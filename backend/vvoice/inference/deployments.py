"""Versioned local deployments: immutable asset hashes, activation and disable state."""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import sqlite3
import threading
from datetime import datetime, timezone

from vvoice.core.errors import ModelConfigurationError


class DeploymentStore:
    def __init__(self, path: Path, profiles):
        self.path = path
        self.profiles = profiles
        self._cache = {}
        self._lock = threading.RLock()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS deployments(
            model_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
            active_version TEXT, activated_at TEXT)''')
        db.execute('''CREATE TABLE IF NOT EXISTS versions(
            version TEXT PRIMARY KEY, model_id TEXT NOT NULL, payload TEXT NOT NULL,
            created_at TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS profiles(
            model_id TEXT PRIMARY KEY, payload TEXT NOT NULL)''')
        return db

    def enabled(self, model_id):
        if not self.path.exists():
            return True
        db = self._connect()
        try:
            row = db.execute('SELECT enabled FROM deployments WHERE model_id=?', (model_id,)).fetchone()
            return bool(row[0]) if row else True
        finally:
            db.close()

    def set_enabled(self, model_id, value):
        self._profile(model_id)
        db = self._connect()
        try:
            with db:
                db.execute('''INSERT INTO deployments(model_id,enabled) VALUES(?,?)
                    ON CONFLICT(model_id) DO UPDATE SET enabled=excluded.enabled''',
                    (model_id, int(value)))
        finally:
            db.close()

    def require_activation_before_enable(self, model_id):
        db = self._connect()
        try:
            state = db.execute('SELECT active_version FROM deployments WHERE model_id=?', (model_id,)).fetchone()
            imported = db.execute('SELECT 1 FROM profiles WHERE model_id=?', (model_id,)).fetchone()
        finally:
            db.close()
        active = state[0] if state else None
        if (imported and not active) or (active and self.snapshot(model_id)['deployment_version'] != active):
            raise ModelConfigurationError('Activate the current deployment before enabling it')

    def _profile(self, model_id):
        if model_id not in self.profiles:
            raise ModelConfigurationError('Unknown model deployment')
        return self.profiles[model_id]

    def snapshot(self, model_id, *, force=False):
        with self._lock:
            profile = self._profile(model_id)
            paths = set()
            # Only declared model assets; never inspect arbitrary environment/user directories.
            for key, value in profile.options.items():
                if key not in {'encoder', 'decoder', 'vocoder', 'tokens', 'lexicon',
                               'model_dir', 'onnx_dir', 'cache_dir', 'data_dir'} or not isinstance(value, (str, Path)):
                    continue
                path = Path(value)
                if not path.is_absolute():
                    path = profile.root / path
                if path.is_file():
                    paths.add(path)
                elif path.is_dir():
                    paths.update(p for p in path.rglob('*') if p.is_file()
                                 and '.locks' not in p.parts and p.suffix != '.lock')
            if profile.engine == 'vieneu':
                model_dir = Path(profile.options.get('model_dir', ''))
                if not model_dir.is_absolute():
                    model_dir = profile.root / model_dir
                source = model_dir.parent / 'manifest.json'
                if source.is_file():
                    paths.add(source)
            signature = tuple(sorted((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in paths))
            options = json.dumps(profile.options, sort_keys=True, default=str)
            cache_key = (signature, options)
            cached = self._cache.get(model_id)
            if not force and cached and cached[0] == cache_key:
                return dict(cached[1])
            files = []
            for path in sorted(paths):
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                # Public job provenance never exposes absolute host paths.
                name = (path.relative_to(profile.root).as_posix()
                        if path.is_relative_to(profile.root) else path.name)
                files.append({'path': name, 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()})
            runtime = {}
            for package in ('onnxruntime', 'torch', 'phonemizer-fork'):
                try:
                    runtime[package] = metadata.version(package)
                except metadata.PackageNotFoundError:
                    pass
            manifest = {'engine': profile.engine, 'model_id': model_id, 'files': files,
                        'sample_rate': profile.sample_rate, 'options_digest': hashlib.sha256(options.encode()).hexdigest(),
                        'runtime_version': runtime, 'text_normalizer_version': 'vassil-brand-nfc-v1'}
            if profile.engine == 'vieneu':
                model_dir = Path(profile.options.get('model_dir', ''))
                if not model_dir.is_absolute():
                    model_dir = profile.root / model_dir
                source = model_dir.parent / 'manifest.json'
                if source.is_file():
                    setup = json.loads(source.read_text(encoding='utf-8'))
                    manifest['sdk'] = setup.get('sdk')
                    manifest['sources'] = setup.get('sources', [])
                    manifest['setup_manifest_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
            version = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
            result = {**manifest, 'deployment_version': version}
            self._cache[model_id] = (cache_key, result)
            return dict(result)

    def activate(self, model_id):
        snapshot = self.snapshot(model_id, force=True)
        now = datetime.now(timezone.utc).isoformat()
        db = self._connect()
        try:
            with db:
                profile = self._profile(model_id)
                definition = dict(model_id=model_id, engine=profile.engine, label=profile.label,
                                  languages=list(profile.languages), sample_rate=profile.sample_rate,
                                  options=profile.options)
                db.execute('INSERT OR IGNORE INTO versions VALUES(?,?,?,?)',
                           (snapshot['deployment_version'], model_id,
                            json.dumps({**snapshot, 'profile': definition}, default=str), now))
                db.execute('''INSERT INTO deployments VALUES(?,1,?,?)
                    ON CONFLICT(model_id) DO UPDATE SET enabled=1,
                    active_version=excluded.active_version,activated_at=excluded.activated_at''',
                    (model_id, snapshot['deployment_version'], now))
        finally:
            db.close()
        return snapshot

    def register(self, definition):
        db = self._connect()
        try:
            with db:
                db.execute('INSERT INTO profiles VALUES(?,?) ON CONFLICT(model_id) DO UPDATE SET payload=excluded.payload',
                           (definition['model_id'], json.dumps(definition, default=str)))
        finally:
            db.close()

    def registrations(self):
        if not self.path.exists():
            return []
        db = self._connect()
        try:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM profiles')]
        finally:
            db.close()

    def version(self, model_id, version):
        db = self._connect()
        try:
            row = db.execute('SELECT payload FROM versions WHERE model_id=? AND version=?',
                             (model_id, version)).fetchone()
            if not row:
                raise ModelConfigurationError('Unknown installed model version')
            return json.loads(row[0])
        finally:
            db.close()

    def list(self):
        db = self._connect()
        try:
            states = {r['model_id']: dict(r) for r in db.execute('SELECT * FROM deployments')}
            versions = [dict(r) for r in db.execute('SELECT version,model_id,created_at FROM versions ORDER BY created_at DESC')]
            return {'deployments': [dict(model_id=model_id, enabled=True, active_version=None,
                    activated_at=None) | states.get(model_id, {}) for model_id in self.profiles],
                    'versions': versions}
        finally:
            db.close()
