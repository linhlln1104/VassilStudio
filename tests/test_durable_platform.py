"""Platform guarantees exercised with small synthetic audio and no ML runtime."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import shutil
import threading
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from vvoice.core.errors import IdempotencyConflictError
from vvoice.core.observability import get_request_id
from vvoice.domains.asr.jobs import AsrJobService
from vvoice.domains.asr.service import Transcription
from vvoice.domains.tts.jobs import TtsJobService
from vvoice.domains.tts.router import router as tts_router
from vvoice.domains.tts.service import GeneratedSpeech
from vvoice.domains.voices.service import VoiceStore
from vvoice.main import register_exception_handlers, register_request_middleware
from vvoice.shared.audio.io import encode_wav
from vvoice.shared.jobs.durable import DurableExecutor
from vvoice.shared.security.auth import Principal, reset_current_principal, set_current_principal


class FakeTts:
    def __init__(self):
        self.calls = []

    def validate_request(self, *, language=None, model_id=None, **_):
        return self.resolve_model_id(language, model_id)

    def resolve_model_id(self, language=None, model_id=None):
        return model_id or "zipvoice-vi"

    def sample_rate_for(self, language=None, model_id=None):
        return 24000

    def synthesize(self, **values):
        self.calls.append({**values, "request_id": get_request_id()})
        return GeneratedSpeech(np.zeros(240, dtype=np.float32), 24000, 0.01)


class FakeAsr:
    def sample_rate_for(self, language=None):
        return 16000

    def transcribe(self, samples, sample_rate, language=None):
        return Transcription("Synthetic transcript", sample_rate)


def reference(tmp_path):
    voices = VoiceStore(tmp_path / "voices")
    wav = encode_wav(np.linspace(-0.1, 0.1, 2400, dtype=np.float32), 24000)
    profile = voices.create(name="Reference", language="vi", reference_text="Original reference",
                            reference_text_source="user", audio_bytes=wav,
                            sample_rate=24000, duration_seconds=0.1)
    return voices, profile, wav


def stop(service):
    service.shutdown()
    service._executor.shutdown(wait=True)


def wait_job(service, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = service.get(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            assert job.status == "succeeded", job.error
            return job
        time.sleep(0.02)
    pytest.fail("Synthetic durable job did not complete")


@contextmanager
def actor(name):
    token = set_current_principal(Principal(name, name, "service", "operator", ("tts:write", "asr:write")))
    try:
        yield
    finally:
        reset_current_principal(token)


def test_api_only_acceptance_is_completed_by_fresh_worker_with_request_trace(tmp_path):
    voices, profile, _ = reference(tmp_path)
    api_runtime = FakeTts()
    queued = TtsJobService(tmp_path / "jobs", api_runtime, voices, worker_enabled=False)
    app = FastAPI()
    app.state.container = SimpleNamespace(tts=api_runtime, tts_jobs=queued, voices=voices,
        settings=SimpleNamespace(security=SimpleNamespace(auth_required=False, api_keys=())))
    app.include_router(tts_router, prefix="/api/v1/tts")
    register_request_middleware(app)
    register_exception_handlers(app)
    try:
        with TestClient(app) as client:
            response = client.post(f"/api/v1/tts/jobs/voices/{profile.voice_id}",
                data={"text": "Persist this accepted request", "language": "vi"},
                headers={"Idempotency-Key": "restart-request", "X-Request-ID": "external-worker-trace"})
        assert response.status_code == 202
        accepted = response.json()
        assert accepted["status"] == "queued" and not api_runtime.calls
        assert accepted["actor_id"] == "local" and accepted["request_id"] == "external-worker-trace"
    finally:
        stop(queued)
    # New runtime/service has no request context from the API process.
    assert get_request_id() is None
    worker_runtime = FakeTts()
    worker = TtsJobService(tmp_path / "jobs", worker_runtime, voices, worker_enabled=True)
    try:
        completed = wait_job(worker, accepted["job_id"])
        assert completed.output_path.is_file()
        assert completed.actor_id == "local" and completed.request_id == "external-worker-trace"
        assert worker_runtime.calls[0]["request_id"] == "external-worker-trace"
        with actor("local"):
            replay = worker.create_from_voice(voice_id=profile.voice_id, text="Persist this accepted request",
                                              language="vi", idempotency_key="restart-request")
        assert replay.job_id == completed.job_id
        assert len(worker_runtime.calls) == 1
    finally:
        stop(worker)


@pytest.mark.parametrize("legacy_absolute", [False, True])
def test_copied_metadata_restores_tts_output_and_asr_input_portably(tmp_path, legacy_absolute):
    voices, profile, wav = reference(tmp_path)
    source = tmp_path / "original"
    tts = TtsJobService(source / "tts", FakeTts(), voices)
    asr = AsrJobService(source / "asr", FakeAsr(), target_sample_rate=16000)
    try:
        tts_job = wait_job(tts, tts.create_from_voice(voice_id=profile.voice_id, text="Portable").job_id)
        asr_job = wait_job(asr, asr.create_from_audio(audio_bytes=wav, filename="reference.wav").job_id)
        expected_output = tts_job.output_path.read_bytes()
        expected_input = asr_job.input_path.read_bytes()
    finally:
        stop(tts)
        stop(asr)
    if legacy_absolute:
        for directory, job_id, key, old_path in (
            ("tts", tts_job.job_id, "output_path", tts_job.output_path),
            ("asr", asr_job.job_id, "input_path", asr_job.input_path),
        ):
            metadata_path = source / directory / job_id / "metadata.json"
            value = json.loads(metadata_path.read_text(encoding="utf-8"))
            value[key] = str(old_path)
            metadata_path.write_text(json.dumps(value), encoding="utf-8")
    restored = tmp_path / "restored"
    shutil.copytree(source, restored)
    recovered_tts = TtsJobService(restored / "tts", FakeTts(), voices, worker_enabled=False)
    recovered_asr = AsrJobService(restored / "asr", FakeAsr(), target_sample_rate=16000, worker_enabled=False)
    try:
        output = recovered_tts.get(tts_job.job_id).output_path
        input_path = recovered_asr.get(asr_job.job_id).input_path
        assert output.is_relative_to(restored) and input_path.is_relative_to(restored)
        assert output.read_bytes() == expected_output and input_path.read_bytes() == expected_input
        assert recovered_tts.quarantined_count == recovered_asr.quarantined_count == 0
    finally:
        stop(recovered_tts)
        stop(recovered_asr)


def test_two_executors_share_queue_and_claim_each_task_once(tmp_path):
    calls = []
    lock = threading.Lock()
    complete = threading.Event()

    def callback(job_id):
        with lock:
            calls.append(job_id)
            if len(calls) == 12:
                complete.set()

    first = DurableExecutor(tmp_path / "queue", callback, max_workers=2, enabled=False)
    second = DurableExecutor(tmp_path / "queue", callback, max_workers=2, enabled=False)
    try:
        for index in range(12):
            first.submit(callback, f"job-{index}")
        first.enabled = second.enabled = True
        starts = [threading.Thread(target=executor.start) for executor in (first, second)]
        for thread in starts:
            thread.start()
        for thread in starts:
            thread.join()
        assert complete.wait(10)
    finally:
        first.shutdown(wait=True)
        second.shutdown(wait=True)
    assert sorted(calls) == sorted(f"job-{index}" for index in range(12))
    assert not first.pending_ids()


def test_manual_retry_reuses_frozen_reference_after_voice_edit_and_delete(tmp_path):
    voices, profile, _ = reference(tmp_path)
    runtime = FakeTts()
    service = TtsJobService(tmp_path / "jobs", runtime, voices)
    try:
        original = wait_job(service, service.create_from_voice(voice_id=profile.voice_id, text="Frozen").job_id)
        voices.update(profile.voice_id, reference_text="Changed after first render")
        voices.delete(profile.voice_id)
        retried = wait_job(service, service.retry(original.job_id, idempotency_key="retry-once").job_id)
        assert retried.job_id != original.job_id
        assert retried.reference_audio_sha256 == original.reference_audio_sha256
        assert retried.reference_text == original.reference_text == "Original reference"
        assert retried.provenance["retry_of"] == original.job_id
        assert len(runtime.calls) == 2
        np.testing.assert_array_equal(runtime.calls[0]["reference_audio"], runtime.calls[1]["reference_audio"])
        assert service.retry(original.job_id, idempotency_key="retry-once").job_id == retried.job_id
    finally:
        stop(service)


@pytest.mark.parametrize("kind", ["tts", "asr"])
def test_idempotency_tombstone_prevents_reexecution_after_cleanup(tmp_path, kind):
    voices, profile, wav = reference(tmp_path)
    service = (TtsJobService(tmp_path / kind, FakeTts(), voices, worker_enabled=False)
               if kind == "tts" else AsrJobService(tmp_path / kind, FakeAsr(), target_sample_rate=16000, worker_enabled=False))

    def create():
        if kind == "tts":
            return service.create_from_voice(voice_id=profile.voice_id, text="Idempotent", idempotency_key="one-request")
        return service.create_from_audio(audio_bytes=wav, filename="input.wav", idempotency_key="one-request")

    try:
        with actor("first-client"):
            original = create()
            assert create().job_id == original.job_id
            service.cancel(original.job_id)
            service.cleanup(max_age_seconds=0)
            with pytest.raises(IdempotencyConflictError, match="removed"):
                create()
        with actor("second-client"):
            # Keys are namespaced by actor, including ASR.
            other = create()
        assert other.job_id != original.job_id and other.actor_id == "second-client"
    finally:
        stop(service)


def test_expired_idempotency_key_starts_new_job_and_then_replays_it(tmp_path):
    voices, profile, _ = reference(tmp_path)
    service = TtsJobService(tmp_path / "jobs", FakeTts(), voices, worker_enabled=False)
    try:
        original = service.create_from_voice(voice_id=profile.voice_id, text="Same request", idempotency_key="expiring")
        service.cancel(original.job_id)
        old = datetime.now(UTC) - timedelta(days=31)
        service._save(replace(service.get(original.job_id), created_at=old.isoformat()))
        with service._executor.connection() as db:
            db.execute("update dedup set expires = ?", (time.time() - 1,))
        fresh = service.create_from_voice(voice_id=profile.voice_id, text="Same request", idempotency_key="expiring")
        assert fresh.job_id != original.job_id
        replay = service.create_from_voice(voice_id=profile.voice_id, text="Same request", idempotency_key="expiring")
        assert replay.job_id == fresh.job_id
        with service._executor.connection() as db:
            expiration = db.execute("select expires from dedup").fetchone()[0]
        assert expiration > time.time() + 29 * 86400
    finally:
        stop(service)


def test_retry_key_cannot_replay_a_different_frozen_source(tmp_path):
    voices, profile, first_wav = reference(tmp_path)
    runtime = FakeTts()
    service = TtsJobService(tmp_path / "jobs", runtime, voices, worker_enabled=False)
    second_wav = encode_wav(np.full(2400, 0.2, dtype=np.float32), 24000)
    try:
        first = service.create_from_snapshot(
            voice_id=profile.voice_id, text="Same script", language="vi",
            reference_bytes=first_wav, reference_text="First reference",
        )
        second = service.create_from_snapshot(
            voice_id=profile.voice_id, text="Same script", language="vi",
            reference_bytes=second_wav, reference_text="Second reference",
        )
        service.cancel(first.job_id)
        service.cancel(second.job_id)
        assert first.reference_audio_sha256 != second.reference_audio_sha256

        first_retry = service.retry(first.job_id, idempotency_key="shared-retry-key")
        with pytest.raises(IdempotencyConflictError, match="different TTS request"):
            service.retry(second.job_id, idempotency_key="shared-retry-key")
        assert len(service.list()) == 3

        second_retry = service.retry(second.job_id, idempotency_key="second-retry-key")
        assert second_retry.job_id != first_retry.job_id
        assert second_retry.reference_audio_sha256 == second.reference_audio_sha256
        assert second_retry.reference_text == "Second reference"
        assert second_retry.provenance["retry_of"] == second.job_id
        assert not runtime.calls
    finally:
        stop(service)


def test_same_source_retry_key_replays_after_service_restart(tmp_path):
    voices, profile, wav = reference(tmp_path)
    runtime = FakeTts()
    directory = tmp_path / "jobs"
    service = TtsJobService(directory, runtime, voices, worker_enabled=False)
    try:
        original = service.create_from_snapshot(
            voice_id=profile.voice_id, text="Retry this snapshot", language="vi",
            reference_bytes=wav, reference_text="Frozen retry reference",
        )
        service.cancel(original.job_id)
        retried = service.retry(original.job_id, idempotency_key="persistent-retry")
        assert service.retry(original.job_id, idempotency_key="persistent-retry").job_id == retried.job_id
    finally:
        stop(service)

    voices.delete(profile.voice_id)
    restarted = TtsJobService(directory, runtime, voices, worker_enabled=False)
    try:
        replay = restarted.retry(original.job_id, idempotency_key="persistent-retry")
        assert replay.job_id == retried.job_id
        assert replay.reference_audio_sha256 == original.reference_audio_sha256
        assert replay.reference_text == "Frozen retry reference"
        assert replay.provenance["retry_of"] == original.job_id
        assert len(restarted.list()) == 2
        assert not runtime.calls
    finally:
        stop(restarted)
