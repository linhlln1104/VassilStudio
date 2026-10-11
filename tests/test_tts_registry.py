from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import numpy as np
import pytest

from vvoice.core.config import parse_settings
from vvoice.core.errors import ModelConfigurationError, VVoiceError
from vvoice.domains.tts.service import TtsService
from vvoice.inference.tts.base import GeneratedSpeech, TtsCapabilities
from vvoice.inference.tts.registry import TtsRegistry
from vvoice.inference.tts.zipvoice.adapter import ZipVoiceAdapter

ROOT = Path(__file__).resolve().parents[1]


class FakeAdapter:
    capabilities = TtsCapabilities()

    def __init__(self, profile, runtime):
        self.profile = profile
        self.loads = 0
        self.calls = []
        self.available = True
        self.closed = False

    def checks(self):
        return {'weights': self.available}

    def load(self):
        self.loads += 1
        if not self.available:
            raise ModelConfigurationError('weights missing')

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return GeneratedSpeech(np.zeros(240, dtype=np.float32), self.profile.sample_rate, 0)

    def close(self):
        self.closed = True


def make_service(tmp_path):
    raw = json.loads((ROOT / 'config/vassil.example.json').read_text())
    raw['tts'] = {
        'default_language': 'vi', 'default_models': {'vi': 'first', 'en': 'second'},
        'profiles': {
            'first': {'engine': 'fake', 'languages': ['vi'], 'sample_rate': 24000},
            'second': {'engine': 'fake', 'languages': ['vi', 'en'], 'sample_rate': 48000},
        },
    }
    settings = parse_settings(raw, tmp_path)
    registry = TtsRegistry()
    adapters = {}
    def create(profile, runtime):
        adapters[profile.model_id] = FakeAdapter(profile, runtime)
        return adapters[profile.model_id]
    registry.register('fake', create)
    return TtsService(settings.tts, settings.runtime, registry), adapters, settings


def test_config_supports_non_zip_profiles_and_two_models_for_one_language(tmp_path):
    service, adapters, _ = make_service(tmp_path)
    assert service.resolve_model_id('vi') == 'first'
    assert service.resolve_model_id('vi', 'second') == 'second'
    assert service.sample_rate_for('vi', 'second') == 48000
    assert service.configured_languages == ('en', 'vi')
    assert all(adapter.loads == 0 for adapter in adapters.values())
    assert len(service.model_catalog()['models']) == 2
    assert all(adapter.loads == 0 for adapter in adapters.values())


def test_selected_model_lazy_load_is_serialized_and_independent(tmp_path):
    service, adapters, _ = make_service(tmp_path)
    gate = threading.Barrier(4)
    def generate():
        gate.wait(timeout=5)
        return service.synthesize(text='hello', reference_text='reference',
            reference_audio=np.zeros(240), reference_sample_rate=24000,
            language='vi', model_id='second')
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: generate(), range(4)))
    assert adapters['first'].loads == 0
    assert adapters['second'].loads == 1
    assert len(adapters['second'].calls) == 4
    assert all(item.sample_rate == 48000 and item.duration_seconds == .005 for item in results)
    assert service.loaded_languages == ('en', 'vi')
    service.close()
    assert all(adapter.closed for adapter in adapters.values())
    assert not service.is_loaded


@pytest.mark.parametrize('kwargs', [
    {'model_id': 'unknown'}, {'model_id': ''},
    {'language': 'en', 'model_id': 'first'},
    {'model_id': 'second', 'num_steps': 4}, {'model_id': 'second', 'speed': 1.2},
])
def test_invalid_model_requests_rejected_before_runtime_load(tmp_path, kwargs):
    service, adapters, _ = make_service(tmp_path)
    with pytest.raises(VVoiceError):
        service.validate_request(**kwargs)
    assert all(adapter.loads == 0 for adapter in adapters.values())


def test_optional_model_missing_does_not_block_defaults(tmp_path):
    service, adapters, settings = make_service(tmp_path)
    # Both languages now default to the bilingual deployment; first is optional.
    service._settings = replace(settings.tts, default_models={'vi': 'second', 'en': 'second'})
    adapters['first'].available = False
    catalog = {item['model_id']: item for item in service.model_catalog()['models']}
    assert not catalog['first']['ready']
    assert catalog['second']['ready']
    assert all(service.readiness_checks().values())
    service.warmup_all()
    assert adapters['second'].loads == 1
    assert adapters['first'].loads == 0


def test_legacy_config_converts_to_stable_profile_ids(tmp_path):
    raw = json.loads((ROOT / 'config/vassil.example.json').read_text())
    zip_profile = raw['tts']['profiles']['zipvoice-vi']
    raw['tts'] = dict(zip_profile['options'], default_language='vi', sample_rate=24000)
    settings = parse_settings(raw, tmp_path)
    assert settings.tts.default_models == {'vi': 'zipvoice-vi'}
    assert settings.tts.profiles['zipvoice-vi'].engine == 'zipvoice'
    assert settings.tts.tokens == tmp_path / zip_profile['options']['tokens']


def test_dead_worker_is_not_reported_loaded_and_can_reload(tmp_path):
    service, adapters, _ = make_service(tmp_path)
    service.warmup('vi', 'second')
    adapters['second'].is_loaded = False
    assert not service.is_loaded
    model = next(item for item in service.model_catalog()['models'] if item['model_id'] == 'second')
    assert not model['loaded']
    service.warmup('vi', 'second')
    assert adapters['second'].loads == 2


def test_failed_initialization_can_recover_without_poisoning_other_model(tmp_path):
    service, adapters, _ = make_service(tmp_path)
    adapters['first'].available = False
    with pytest.raises(ModelConfigurationError):
        service.warmup('vi', 'first')
    service.warmup('vi', 'second')
    assert service.is_loaded
    assert not all(service.readiness_checks().values())
    adapters['first'].available = True
    service.warmup('vi', 'first')
    assert all(service.readiness_checks().values())


def test_partial_load_is_closed_and_original_error_is_preserved(tmp_path):
    service, adapters, _ = make_service(tmp_path)
    resources = []
    def fail_load():
        resources.append(object())
        raise ModelConfigurationError('decoder failed')
    def fail_close():
        resources.clear()
        raise RuntimeError('cleanup warning')
    adapters['first'].load = fail_load
    adapters['first'].close = fail_close
    with pytest.raises(ModelConfigurationError, match='decoder failed'):
        service.warmup('vi', 'first')
    assert resources == []
    assert not service.is_loaded
    assert not adapters['second'].closed


def test_closed_service_cannot_warmup_or_generate(tmp_path):
    service, adapters, _ = make_service(tmp_path)
    service.close()
    with pytest.raises(ModelConfigurationError, match='shutting down'):
        service.warmup('vi', 'first')
    with pytest.raises(ModelConfigurationError, match='shutting down'):
        service.synthesize(text='hello', reference_text='reference',
            reference_audio=np.zeros(240), reference_sample_rate=24000)
    assert all(adapter.loads == 0 for adapter in adapters.values())


def test_request_admitted_before_shutdown_cannot_resurrect_model(tmp_path):
    service, adapters, _ = make_service(tmp_path)
    admitted = threading.Event()
    resume = threading.Event()
    original_validate = service.validate_request
    def delayed_validate(**kwargs):
        selected = original_validate(**kwargs)
        admitted.set()
        assert resume.wait(timeout=5)
        return selected
    service.validate_request = delayed_validate
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.synthesize, text='hello', reference_text='reference',
            reference_audio=np.zeros(240), reference_sample_rate=24000)
        try:
            assert admitted.wait(timeout=5)
            service.close()
        finally:
            resume.set()
        with pytest.raises(ModelConfigurationError, match='shutting down'):
            future.result(timeout=5)
    assert all(adapter.loads == 0 for adapter in adapters.values())


@pytest.mark.parametrize('option,value', [
    ('default_num_steps', 0), ('default_num_steps', 100000),
    ('default_speed', 0.1), ('default_speed', 5), ('default_speed', float('nan')),
])
def test_invalid_configured_zip_defaults_rejected_before_loading(tmp_path, option, value):
    raw = json.loads((ROOT / 'config/vassil.example.json').read_text())
    raw['tts']['profiles']['zipvoice-vi']['options'][option] = value
    settings = parse_settings(raw, tmp_path)
    with pytest.raises(ModelConfigurationError, match='Invalid ZipVoice defaults'):
        ZipVoiceAdapter(settings.tts.profiles['zipvoice-vi'], settings.runtime)


def test_zipvoice_load_does_not_require_unused_legacy_assets(tmp_path, monkeypatch):
    raw = json.loads((ROOT / 'config/vassil.example.json').read_text())
    settings = parse_settings(raw, tmp_path)
    adapter = ZipVoiceAdapter(settings.tts.profiles['zipvoice-vi'], settings.runtime)
    for name in ('tokens', 'encoder', 'decoder', 'vocoder'):
        path = getattr(adapter.model, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'asset')
    monkeypatch.setattr('vvoice.inference.tts.zipvoice.adapter.module_available', lambda name: True)
    loaded = []
    monkeypatch.setattr(adapter._runtime, 'load', lambda: loaded.append(True))
    assert not adapter.model.lexicon.exists()
    assert not adapter.model.data_dir.exists()
    adapter.load()
    assert loaded == [True]


@pytest.mark.parametrize('change', [
    lambda tts: tts.update(default_models={'vi': 'unknown'}),
    lambda tts: tts.update(default_models={'vi': 'second'}),
    lambda tts: tts['profiles']['first'].update(languages=[]),
    lambda tts: tts['profiles']['first'].update(sample_rate=0),
])
def test_invalid_profile_config_rejected(tmp_path, change):
    _, _, settings = make_service(tmp_path)
    raw = json.loads((ROOT / 'config/vassil.example.json').read_text())
    raw['tts'] = {'default_language':'vi', 'default_models':{'vi':'first','en':'second'},
        'profiles': {model_id: {'engine':p.engine,'languages':list(p.languages),
                               'sample_rate':p.sample_rate} for model_id,p in settings.tts.profiles.items()}}
    change(raw['tts'])
    with pytest.raises((ValueError, VVoiceError)):
        parse_settings(raw, tmp_path)
