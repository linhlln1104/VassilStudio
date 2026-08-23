from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from vvoice.core.errors import VVoiceError, VoiceDuplicateError, VoiceNotFoundError
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language


AUDIO_IMPORT_EXTENSIONS = {".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".weba", ".webm"}


@dataclass(frozen=True)
class VoiceProfile:
    voice_id: str
    name: str
    language: str
    reference_text: str
    reference_text_source: str
    audio_path: Path
    audio_size_bytes: int
    sample_rate: int
    duration_seconds: float
    created_at: str
    updated_at: str | None = None
    audio_sha256: str = ""


class VoiceStore:
    def __init__(self, voices_dir: Path) -> None:
        self._voices_dir = voices_dir
        self._lock = RLock()

    def create(
        self,
        *,
        name: str,
        language: str = DEFAULT_LANGUAGE,
        reference_text: str,
        reference_text_source: str,
        audio_bytes: bytes,
        sample_rate: int,
        duration_seconds: float,
        audio_sha256: str | None = None,
    ) -> VoiceProfile:
        canonical_hash = hashlib.sha256(audio_bytes).hexdigest()
        if audio_sha256 is not None and audio_sha256 != canonical_hash:
            raise VVoiceError("audio_sha256 does not match the canonical voice audio")
        with self._lock:
            duplicate = self.find_by_audio_sha256(canonical_hash)
            if duplicate is not None:
                raise VoiceDuplicateError(
                    f'Audio already belongs to voice profile "{duplicate.name}". '
                    "Reuse that profile instead of creating a duplicate."
                )

            self._voices_dir.mkdir(parents=True, exist_ok=True)
            voice_id = str(uuid.uuid4())
            voice_dir = self._voices_dir / voice_id
            voice_dir.mkdir(parents=True, exist_ok=False)
            created_at = datetime.now(tz=timezone.utc).isoformat()
            language = normalize_language(language)

            audio_path = voice_dir / "reference.wav"
            audio_path.write_bytes(audio_bytes)
            metadata = {
                "metadata_version": 4,
                "voice_id": voice_id,
                "name": name,
                "language": language,
                "reference_text": reference_text,
                "reference_text_source": reference_text_source,
                "audio_path": audio_path.name,
                "audio_sha256": canonical_hash,
                "audio_size_bytes": len(audio_bytes),
                "sample_rate": sample_rate,
                "duration_seconds": duration_seconds,
                "created_at": created_at,
                "updated_at": created_at,
            }
            (voice_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return VoiceProfile(
                voice_id=voice_id,
                name=name,
                language=language,
                reference_text=reference_text,
                reference_text_source=reference_text_source,
                audio_path=audio_path,
                audio_size_bytes=len(audio_bytes),
                sample_rate=sample_rate,
                duration_seconds=duration_seconds,
                created_at=created_at,
                updated_at=created_at,
                audio_sha256=canonical_hash,
            )

    def list(self) -> list[VoiceProfile]:
        with self._lock:
            if not self._voices_dir.exists():
                return []

            profiles: list[VoiceProfile] = []
            for metadata_path in self._voices_dir.glob("*/metadata.json"):
                profiles.append(_load_profile(metadata_path))
            return sorted(profiles, key=lambda item: item.created_at, reverse=True)

    def find_by_audio_sha256(self, audio_sha256: str) -> VoiceProfile | None:
        with self._lock:
            for profile in self.list():
                profile_hash = profile.audio_sha256
                if not profile_hash and profile.audio_path.is_file():
                    profile_hash = hashlib.sha256(profile.audio_path.read_bytes()).hexdigest()
                if profile_hash == audio_sha256:
                    return profile
        return None

    def list_import_candidates(self) -> list[Path]:
        with self._lock:
            if not self._voices_dir.exists():
                return []

            return sorted(
                [
                    path
                    for path in self._voices_dir.iterdir()
                    if path.is_file() and path.suffix.lower() in AUDIO_IMPORT_EXTENSIONS
                ],
                key=lambda item: item.name.lower(),
            )

    def import_candidate_path(self, filename: str) -> Path:
        with self._lock:
            if Path(filename).name != filename or filename in {"", ".", ".."}:
                raise VVoiceError(f"Invalid voice import filename: {filename}")

            path = self._voices_dir / filename
            if not path.exists() or not path.is_file():
                raise VoiceNotFoundError(f"Voice import file not found: {filename}")
            if path.suffix.lower() not in AUDIO_IMPORT_EXTENSIONS:
                raise VVoiceError(f"Unsupported voice import file type: {path.suffix}")
            return path

    def get(self, voice_id: str) -> VoiceProfile:
        with self._lock:
            metadata_path = self._voices_dir / voice_id / "metadata.json"
            if not metadata_path.exists():
                raise VoiceNotFoundError(f"Voice profile not found: {voice_id}")

            profile = _load_profile(metadata_path)
            if not profile.audio_path.exists():
                raise VoiceNotFoundError(f"Voice profile audio is missing: {voice_id}")
            return profile

    def update(
        self,
        voice_id: str,
        *,
        name: str | None = None,
        language: str | None = None,
        reference_text: str | None = None,
    ) -> VoiceProfile:
        with self._lock:
            metadata_path = self._voices_dir / voice_id / "metadata.json"
            if not metadata_path.exists():
                raise VoiceNotFoundError(f"Voice profile not found: {voice_id}")

            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            if name is not None:
                raw["name"] = name
            if language is not None:
                raw["language"] = normalize_language(language)
            if reference_text is not None:
                raw["reference_text"] = reference_text
                raw["reference_text_source"] = "user"
            raw["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

            metadata_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return self.get(voice_id)

    def delete(self, voice_id: str) -> None:
        with self._lock:
            voice_dir = self._voices_dir / voice_id
            if not voice_dir.exists():
                raise VoiceNotFoundError(f"Voice profile not found: {voice_id}")

            for path in voice_dir.glob("*"):
                if path.is_file():
                    path.unlink()
            voice_dir.rmdir()


def _load_profile(metadata_path: Path) -> VoiceProfile:
    raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    return _profile_from_metadata(raw, metadata_path.parent)


def _profile_from_metadata(raw: dict, voice_dir: Path) -> VoiceProfile:
    audio_path = _resolve_audio_path(voice_dir, raw["audio_path"])
    return VoiceProfile(
        voice_id=raw["voice_id"],
        name=raw["name"],
        language=normalize_language(raw.get("language")),
        reference_text=raw["reference_text"],
        reference_text_source=str(raw.get("reference_text_source", "user")),
        audio_path=audio_path,
        audio_size_bytes=int(raw.get("audio_size_bytes") or _file_size(audio_path)),
        sample_rate=int(raw.get("sample_rate", 0)),
        duration_seconds=float(raw.get("duration_seconds", 0.0)),
        created_at=str(raw.get("created_at", "")),
        updated_at=raw.get("updated_at"),
        audio_sha256=str(raw.get("audio_sha256", "")),
    )


def _resolve_audio_path(voice_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else voice_dir / path


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0
