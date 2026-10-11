from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import uuid
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from vvoice.core.errors import JobQueueFullError, TtsJobNotFoundError
from vvoice.core.observability import reset_request_id, set_request_id
from vvoice.domains.production.router import router
from vvoice.domains.production.schemas import BatchInput
from vvoice.domains.production.service import ProductionError, ProductionService
from vvoice.shared.security.auth import require_api_key
from vvoice.shared.security.principal import Principal


OWNER = Principal("owner", "Owner", "user", "owner", ("*",))
EDITOR = Principal("editor", "Editor", "user", "editor", ("production:read", "production:write"))
REVIEWER = Principal("reviewer", "Reviewer", "user", "reviewer", ("production:read", "production:review"))
OUTSIDER = Principal("outsider", "Outsider", "user", "editor", ("production:read", "production:write"))


class FakeTts:
    version = "model-v1"

    def resolve_parameters(self, language=None, model_id=None, num_steps=None, speed=None):
        if model_id not in (None, "test-model"):
            raise ValueError("Unknown model")
        return {"model_id": "test-model", "language": language or "vi",
                "num_steps": num_steps or 8, "speed": speed or 1.0,
                "deployment_version": self.version, "engine": "test", "runtime_version": "1",
                "text_normalizer_version": "1", "model_manifest": {"sha256": "test-sha"}}

    def model_catalog(self):
        return {"models": [{"model_id": "test-model", "ready": True}]}


class FakeVoices:
    def get(self, voice_id):
        if voice_id != "voice":
            raise ValueError("Unknown voice")
        return SimpleNamespace(language="vi")


class FakeJobs:
    def __init__(self, directory, capacity=2):
        self.directory = Path(directory)
        self.directory.mkdir(exist_ok=True)
        self.capacity = capacity
        self.jobs = {}
        self.keys = {}
        self.calls = []
        self.reference = b"original reference"

    def snapshot_voice(self, voice_id):
        FakeVoices().get(voice_id)
        return {"voice_id": voice_id, "language": "vi", "reference_wav": self.reference,
                "reference_audio_sha256": hashlib.sha256(self.reference).hexdigest(),
                "reference_text": "reference transcript"}

    def create_from_snapshot(self, **kwargs):
        key = kwargs["idempotency_key"]
        if key in self.keys:
            return self.jobs[self.keys[key]]
        if sum(job.status not in {"succeeded", "failed", "cancelled"}
               for job in self.jobs.values()) >= self.capacity:
            raise JobQueueFullError("full")
        job_id = str(uuid.uuid4())
        job = SimpleNamespace(job_id=job_id, status="queued", output_path=self.directory / (job_id + ".wav"),
                              sample_rate=24000, duration_seconds=1, provenance=kwargs["provenance"])
        self.jobs[job_id], self.keys[key] = job, job_id
        self.calls.append(kwargs)
        return job

    def get(self, job_id):
        if job_id not in self.jobs:
            raise TtsJobNotFoundError("missing job")
        return self.jobs[job_id]

    def cancel(self, job_id):
        self.jobs[job_id].status = "cancelled"
        return self.jobs[job_id]

    def complete(self, job_id, *, failed=False):
        job = self.jobs[job_id]
        job.status = "failed" if failed else "succeeded"
        if not failed:
            job.output_path.write_bytes(b"RIFF retained generated audio " + job_id.encode())


@pytest.fixture
def env(tmp_path):
    jobs = FakeJobs(tmp_path / "jobs")
    service = ProductionService(tmp_path / "production", jobs, FakeTts(), FakeVoices())
    project = service.create_project({"name": "Project"}, OWNER)
    app = FastAPI()
    app.state.container = SimpleNamespace(production=service)
    app.dependency_overrides[require_api_key] = lambda: OWNER
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        yield SimpleNamespace(service=service, jobs=jobs, project=project,
                              client=client, app=app, path=tmp_path)
    service.shutdown()


def segment(env, **kwargs):
    return env.service.create_segment(env.project["project_id"], {
        "text": "Hello product", "voice_id": "voice", "language": "vi", **kwargs,
    }, OWNER)


def payload(env, count=3):
    return BatchInput(project_id=env.project["project_id"], defaults={"voice_id": "voice"},
                      rows=[{"external_id": f"source-{i}", "text": f"Text {i}"}
                            for i in range(count)]).model_dump()


def finish(env, take):
    env.service.tick()
    current = env.service.list_takes(env.project["project_id"], take["segment_id"], OWNER)["items"][0]
    env.jobs.complete(current["job_id"])
    env.service.tick()
    return env.service.list_takes(env.project["project_id"], take["segment_id"], OWNER)["items"][0]


def test_script_optimistic_revision_and_dictionary_are_snapshotted(env):
    project_id = env.project["project_id"]
    dictionary = env.service.update_dictionary(project_id, {"expected_revision": 1,
        "entries": [{"source": "product", "replacement": "pronunciation", "language": "vi"}]}, OWNER)
    script = segment(env)
    take = env.service.create_take(project_id, script["segment_id"], {"expected_revision": 1}, OWNER)
    env.jobs.reference = b"edited voice"
    env.service.update_dictionary(project_id, {"expected_revision": dictionary["revision"], "entries": []}, OWNER)
    updated = env.service.update_segment(project_id, script["segment_id"],
                                         {"expected_revision": 1, "text": "new script"}, OWNER)
    with pytest.raises(ProductionError, match="Revision changed"):
        env.service.update_segment(project_id, script["segment_id"], {"expected_revision": 1, "text": "stale"}, OWNER)
    env.service.tick()
    assert env.jobs.calls[0]["text"] == "Hello pronunciation"
    assert env.jobs.calls[0]["reference_bytes"] == b"original reference"
    assert env.jobs.calls[0]["actor_id"] == OWNER.principal_id
    assert take["provenance"]["production"]["dictionary_revision"] == 2
    assert updated["script_revision"] == 2
    assert len(env.service.segment_revisions(project_id, script["segment_id"], OWNER)["items"]) == 2


def test_dictionary_is_literal_single_pass_and_language_scoped():
    dictionary = {"entries": [{"source": "A+B", "replacement": "C", "language": None},
                               {"source": "C", "replacement": "D", "language": None},
                               {"source": "cat", "replacement": "mèo", "language": "vi"}]}
    assert ProductionService.apply_dictionary("A+B C cat scatter", "vi", dictionary) == "C D mèo scatter"
    assert ProductionService.apply_dictionary("cat", "en", dictionary) == "cat"


def test_large_batch_backpressure_resume_and_idempotent_creation(env):
    data = payload(env, count=41)
    batch = env.service.create_batch(data, OWNER, idempotency_key="import-1")
    assert env.service.create_batch(data, OWNER, idempotency_key="import-1")["batch_id"] == batch["batch_id"]
    assert not env.jobs.calls
    env.service.tick()
    assert len(env.jobs.calls) == 2
    assert env.service.get_batch(batch["batch_id"], OWNER)["counts"]["pending"] == 39
    restarted = ProductionService(env.path / "production", env.jobs, FakeTts(), FakeVoices())
    for _ in range(30):
        for job in env.jobs.jobs.values():
            if job.status == "queued":
                env.jobs.complete(job.job_id)
        restarted.tick()
        if restarted.get_batch(batch["batch_id"], OWNER)["status"] == "succeeded":
            break
    assert restarted.get_batch(batch["batch_id"], OWNER)["counts"]["succeeded"] == 41
    assert len(env.jobs.calls) == 41
    assert restarted.batch_items(batch["batch_id"], OWNER, limit=5, offset=35)["total"] == 41
    restarted.shutdown()


def test_two_dispatchers_and_crash_window_do_not_duplicate_jobs(env):
    batch = env.service.create_batch(payload(env, 2), OWNER)
    sibling = ProductionService(env.path / "production", env.jobs, FakeTts(), FakeVoices())
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda service: service.tick(), (env.service, sibling)))
    assert len(env.jobs.calls) == 2
    # Queue accepted the first request but its production transaction was lost.
    item = env.service.batch_items(batch["batch_id"], OWNER)["items"][0]
    with env.service.store.transaction() as db:
        take = env.service.store.get(db, "take", item["take_id"])
        take.update(status="pending", job_id=None)
        env.service.store.put(db, "take", take["take_id"], take)
    sibling.tick()
    assert len(env.jobs.calls) == 2
    assert env.service.batch_items(batch["batch_id"], OWNER)["items"][0]["job_id"] == item["job_id"]
    sibling.shutdown()


def test_request_id_survives_pending_take_dispatch_after_restart(env):
    token = set_request_id("batch-http-request")
    try:
        batch = env.service.create_batch(payload(env, 1), OWNER)
    finally:
        reset_request_id(token)
    restarted = ProductionService(env.path / "production", env.jobs, FakeTts(), FakeVoices())
    restarted.tick()
    assert env.jobs.calls[0]["request_id"] == "batch-http-request"
    assert restarted.batch_items(batch["batch_id"], OWNER)["items"][0]["request_id"] == "batch-http-request"
    restarted.shutdown()


def test_retry_failed_only_preserves_successes_and_review_history(env):
    batch = env.service.create_batch(payload(env, 2), OWNER)
    env.service.tick()
    items = env.service.batch_items(batch["batch_id"], OWNER)["items"]
    env.jobs.complete(items[0]["job_id"])
    env.jobs.complete(items[1]["job_id"], failed=True)
    env.service.tick()
    env.service.retry_failed(batch["batch_id"], OWNER)
    retried = env.service.batch_items(batch["batch_id"], OWNER)["items"]
    assert retried[0]["take_id"] == items[0]["take_id"]
    assert retried[1]["take_id"] != items[1]["take_id"]
    assert retried[1]["take_ids"][0] == items[1]["take_id"]
    assert retried[1]["attempt"] == 2
    env.service.tick()
    assert len(env.jobs.calls) == 3


def test_cancel_batch_never_dispatches_pending_rows(env):
    batch = env.service.create_batch(payload(env, 8), OWNER)
    env.service.tick()
    env.service.cancel_batch(batch["batch_id"], OWNER)
    env.service.tick()
    result = env.service.get_batch(batch["batch_id"], OWNER)
    assert result["counts"]["cancelled"] == 8
    assert len(env.jobs.calls) == 2


def test_csv_preflight_catches_ids_options_and_untrusted_columns(env):
    data = BatchInput(project_id=env.project["project_id"], defaults={"voice_id": "voice"},
                      csv_text='external_id,text,callback_url\n001,"first, quoted",https://example.com\n001,next,\n').model_dump()
    result = env.service.analyze_batch(data, OWNER)
    assert not result["can_submit"]
    assert result["rows"][0]["external_id"] == "001"
    assert result["rows"][0]["text"] == "first, quoted"
    assert any("Unknown columns" in value for value in result["rows"][0]["errors"])
    assert any("Duplicate external_id" in value for value in result["rows"][1]["errors"])
    assert not env.jobs.calls
    with pytest.raises(ProductionError):
        env.service.create_batch(data, OWNER)


def test_preflight_token_rejects_changed_dictionary_and_fractional_steps(env):
    data = payload(env, 1)
    data["preflight_token"] = env.service.analyze_batch(data, OWNER)["preflight_token"]
    env.service.update_dictionary(env.project["project_id"], {"expected_revision": 1,
        "entries": [{"source": "Text", "replacement": "Speech"}]}, OWNER)
    with pytest.raises(ProductionError, match="Preflight changed"):
        env.service.create_batch(data, OWNER)
    data["preflight_token"] = None
    data["rows"][0]["num_steps"] = 2.4
    assert not env.service.analyze_batch(data, OWNER)["can_submit"]
    revisions = env.service.dictionary_revisions(env.project["project_id"], OWNER)["items"]
    assert [item["revision"] for item in revisions] == [2, 1]


def test_approved_audio_survives_job_cleanup_and_export_names_are_safe(env):
    data = payload(env, 1)
    data["rows"][0]["external_id"] = "../../CON\\secret:voice"
    batch = env.service.create_batch(data, OWNER)
    take = env.service.batch_items(batch["batch_id"], OWNER)["items"][0]
    take = finish(env, take)
    approved = env.service.review_take(env.project["project_id"], take["take_id"], {
        "expected_revision": take["revision"], "status": "approved", "note": "Good pronunciation",
    }, OWNER)
    env.jobs.get(approved["job_id"]).output_path.unlink()
    env.jobs.jobs.clear()
    archive = env.service.export(OWNER, batch_id=batch["batch_id"])
    with zipfile.ZipFile(archive) as bundle:
        assert all(".." not in path and "\\" not in path for path in bundle.namelist())
        manifest = json.loads(bundle.read("manifest.json"))
        item = manifest["items"][0]
        assert item["external_id"] == "../../CON\\secret:voice"
        assert item["review_note"] == "Good pronunciation"
        assert hashlib.sha256(bundle.read(item["file"])).hexdigest() == item["output_sha256"]
        assert "reference_text" not in item


def test_project_acl_and_review_scope_are_enforced_at_http_layer(env):
    project_id = env.project["project_id"]
    env.service.update_members(project_id, {"expected_revision": 1, "members": [
        {"principal_id": EDITOR.principal_id, "role": "editor"},
        {"principal_id": REVIEWER.principal_id, "role": "reviewer"},
    ]}, OWNER)
    env.app.dependency_overrides[require_api_key] = lambda: OUTSIDER
    assert env.client.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert env.client.get("/api/v1/projects").json()["total"] == 0
    env.app.dependency_overrides[require_api_key] = lambda: REVIEWER
    assert env.client.post(f"/api/v1/projects/{project_id}/segments", json={"text": "new"}).status_code == 403
    env.app.dependency_overrides[require_api_key] = lambda: EDITOR
    assert env.client.patch(f"/api/v1/projects/{project_id}/takes/random/review", json={
        "expected_revision": 1, "status": "approved",
    }).status_code == 403
    assert env.client.put(f"/api/v1/projects/{project_id}/members", json={
        "expected_revision": 2, "members": [],
    }).status_code == 403


def test_http_conflicts_preflight_and_export_openapi(env):
    pid = env.project["project_id"]
    created = env.client.post(f"/api/v1/projects/{pid}/segments", json={"text": "first", "voice_id": "voice"})
    assert created.status_code == 201
    sid = created.json()["segment_id"]
    response = env.client.patch(f"/api/v1/projects/{pid}/segments/{sid}", json={"expected_revision": 99, "text": "stale"})
    assert response.status_code == 409
    analyzed = env.client.post("/api/v1/batches/analyze", json=payload(env))
    assert analyzed.status_code == 200 and analyzed.json()["can_submit"]
    created_batch = env.client.post("/api/v1/batches", json=payload(env), headers={"Idempotency-Key": "key"})
    assert created_batch.status_code == 202
    assert env.client.get(f"/api/v1/batches/{created_batch.json()['batch_id']}/export").status_code == 409
    spec = env.app.openapi()
    audio_response = spec["paths"]["/api/v1/projects/{project_id}/takes/{take_id}/audio"]["get"]["responses"]["200"]
    assert "audio/wav" in audio_response["content"]


def test_selected_take_cannot_silently_follow_script_edit_and_checksum_tampering(env):
    pid = env.project["project_id"]
    script = segment(env)
    take = env.service.create_take(pid, script["segment_id"], {"expected_revision": 1}, OWNER)
    take = finish(env, take)
    env.service.review_take(pid, take["take_id"], {"expected_revision": take["revision"], "status": "approved"}, OWNER)
    selected = env.service.select_take(pid, script["segment_id"], {"expected_revision": 1, "take_id": take["take_id"]}, OWNER)
    env.service.take_audio(pid, take["take_id"], OWNER).write_bytes(b"tampered")
    with pytest.raises(ProductionError, match="checksum"):
        env.service.export(OWNER, project_id=pid)
    changed = env.service.update_segment(pid, script["segment_id"], {"expected_revision": selected["revision"], "text": "changed"}, OWNER)
    assert changed["selected_take_id"] is None
    with pytest.raises(ProductionError, match="older script"):
        env.service.select_take(pid, script["segment_id"], {"expected_revision": changed["revision"], "take_id": take["take_id"]}, OWNER)
