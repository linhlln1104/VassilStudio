import json
from pathlib import Path

import numpy as np
import pytest

from vvoice.core.config import parse_settings
from vvoice.core.errors import ModelConfigurationError
from vvoice.domains.tts.service import TtsService
from vvoice.inference.deployments import DeploymentStore
from vvoice.inference.tts.base import GeneratedSpeech, TtsCapabilities
from vvoice.inference.tts.registry import TtsRegistry


class Adapter:
    capabilities = TtsCapabilities(num_steps=True, speed=True)

    def __init__(self, profile, runtime):
        self.profile, self.loads, self.closes = profile, 0, 0

    def checks(self):
        return {'weights': (self.profile.root / self.profile.options['encoder']).is_file()}

    def load(self):
        self.loads += 1

    def close(self):
        self.closes += 1

    def synthesize(self, **kwargs):
        return GeneratedSpeech(np.zeros(240, dtype=np.float32), self.profile.sample_rate, .01)


def configured(tmp_path):
    (tmp_path / 'weights.onnx').write_bytes(b'version-one')
    raw = json.loads((Path(__file__).parents[1] / 'config/vassil.example.json').read_text())
    profile = {'engine': 'zipvoice', 'languages': ['en'], 'sample_rate': 24000,
               'options': {'encoder': 'weights.onnx', 'decoder': 'weights.onnx',
                           'vocoder': 'weights.onnx', 'tokens': 'weights.onnx',
                           'data_dir': 'espeak-data', 'default_num_steps': 8}}
    raw['tts'] = {'default_language': 'vi', 'default_models': {'en': 'english', 'vi': 'vietnamese'},
                  'profiles': {'english': profile, 'vietnamese': dict(profile, languages=['vi'])}}
    settings = parse_settings(raw, tmp_path)
    registry = TtsRegistry()
    registry.register('zipvoice', Adapter)
    return TtsService(settings.tts, settings.runtime, registry), settings, registry


def test_model_only_warmup_uses_its_language_and_loaded_version_tracks_assets(tmp_path):
    service, _, _ = configured(tmp_path)
    try:
        service.warmup(model_id='english')
        assert service._adapters['english'].loads == 1
        accepted = service.resolve_parameters(language='en')['deployment_version']
        service.warmup(model_id='english')
        assert service._adapters['english'].loads == 1
        (tmp_path / 'weights.onnx').write_bytes(b'changed-weight-content')
        with pytest.raises(ModelConfigurationError, match='accepted model assets changed'):
            with service.deployment_guard('english', accepted):
                pytest.fail('Changed assets may not execute the accepted snapshot')
        service.warmup(model_id='english')
        assert service._adapters['english'].loads == 2
        assert service._adapters['english'].closes == 1
    finally:
        service.close()


def test_import_requires_activation_and_survives_service_restart(tmp_path):
    service, settings, registry = configured(tmp_path)
    definition = {'model_id': 'alternative', 'engine': 'zipvoice', 'languages': ['vi'],
                  'sample_rate': 24000, 'options': {'encoder': 'weights.onnx'}}
    service.import_profile(definition)
    with pytest.raises(ModelConfigurationError, match='disabled'):
        service.resolve_parameters(language='vi', model_id='alternative')
    with pytest.raises(ModelConfigurationError, match='Activate'):
        service.set_enabled('alternative', True)
    activated = service.activate('alternative')
    service.close()
    restored = TtsService(settings.tts, settings.runtime, registry)
    try:
        assert restored.resolve_parameters(model_id='alternative')['deployment_version'] == activated['deployment_version']
        restored.set_enabled('alternative', False)
        assert not next(m for m in restored.model_catalog()['models'] if m['model_id'] == 'alternative')['ready']
    finally:
        restored.close()


def test_rollback_restores_recorded_parameters_but_refuses_replaced_weights(tmp_path):
    service, _, _ = configured(tmp_path)
    try:
        first = service.activate('english')['deployment_version']
        service.import_profile({'model_id': 'english', 'engine': 'zipvoice', 'languages': ['en'],
            'sample_rate': 24000, 'options': {'encoder': 'weights.onnx', 'default_num_steps': 16}})
        assert service.activate('english')['deployment_version'] != first
        service.rollback('english', first)
        assert service.resolve_parameters(language='en')['num_steps'] == 8
        (tmp_path / 'weights.onnx').write_bytes(b'replaced-weights')
        with pytest.raises(ModelConfigurationError, match='Restore the recorded weights'):
            service.rollback('english', first)
    finally:
        service.close()


def test_vieneu_version_includes_codec_blobs_and_setup_manifest(tmp_path):
    from dataclasses import replace
    _, settings, _ = configured(tmp_path)
    model = tmp_path / 'model'
    cache = tmp_path / 'cache'
    model.mkdir()
    cache.mkdir()
    (model / 'weights.onnx').write_bytes(b'model')
    (cache / 'blob-without-extension').write_bytes(b'codec-one')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{"sdk": "first"}')
    profile = replace(settings.tts.profiles['english'], engine='vieneu',
                      options={'model_dir': 'model', 'cache_dir': 'cache'})
    store = DeploymentStore(tmp_path / 'versions.sqlite3', {'english': profile})
    first = store.snapshot('english')['deployment_version']
    (cache / 'blob-without-extension').write_bytes(b'codec-two-and-more')
    second = store.snapshot('english')['deployment_version']
    assert first != second
    manifest.write_text('{"sdk": "changed"}')
    assert store.snapshot('english')['deployment_version'] != second
