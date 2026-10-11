from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from vvoice.app.auth.service import LocalAuthService
from vvoice.core.config import SecuritySettings
from vvoice.core.errors import VVoiceError
from vvoice.domains.asr.router import router as asr_router
from vvoice.domains.tts.router import router as tts_router


class Jobs:
    def __init__(self, jobs):
        self.jobs = {job.job_id: job for job in jobs}
        self.mutations = []

    def list(self, **_):
        return list(self.jobs.values())

    def get(self, job_id):
        return self.jobs[job_id]

    def delete(self, job_id):
        self.mutations.append(("delete", job_id))

    def cancel(self, job_id):
        self.mutations.append(("cancel", job_id))
        return self.get(job_id)

    def retry(self, job_id, **_):
        self.mutations.append(("retry", job_id))
        return self.get(job_id)


class Projects:
    def __init__(self):
        self.allowed = {}

    def assert_project_access(self, project_id, principal, action="read"):
        if action not in self.allowed.get((project_id, principal.principal_id), set()):
            raise VVoiceError("Project not found")


def job(tmp_path, job_id, actor_id, project_id=None):
    path = tmp_path / f"{job_id}.wav"
    path.write_bytes(b"test-audio")
    return SimpleNamespace(
        job_id=job_id, actor_id=actor_id, status="succeeded", voice_id="voice", language="vi",
        model_id="demo", text="Example", num_steps=None, speed=None,
        created_at="2026-01-01T00:00:00Z", started_at=None, completed_at="2026-01-01T00:00:01Z",
        error=None, attempt=1, max_attempts=1, cancel_requested=False, failed_reason=None,
        progress_stage="succeeded", stage_started_at="2026-01-01T00:00:01Z", sample_rate=24000,
        duration_seconds=1.0, output_path=path, input_path=path,
        request_id="trace", recovery_count=1, provenance={"production": {"project_id": project_id}} if project_id else {},
        filename="input.wav", raw_text="Example", raw_segments=(), segments=(),
        timing_status="unavailable", transcript_revision=0, transcript_updated_at=None,
    )


@pytest.fixture
def env(tmp_path):
    settings = SecuritySettings(api_keys=("admin-key",), auth_required=True,
        auth_db_path=tmp_path / "auth.sqlite3", session_cookie_name="session", session_ttl_seconds=3600,
        session_secret="secret", secure_cookies=False)
    auth = LocalAuthService(settings)
    owner = auth.create_service_account("owner", "operator")
    other = auth.create_service_account("other", "operator")
    token = auth.create_api_key(owner["principal_id"], "test")["token"]
    records = [job(tmp_path, "foreign", other["principal_id"]), job(tmp_path, "own", owner["principal_id"]),
               job(tmp_path, "legacy", None), job(tmp_path, "project", owner["principal_id"], "private-project")]
    jobs = Jobs(records)
    projects = Projects()
    app = FastAPI()
    app.state.container = SimpleNamespace(settings=SimpleNamespace(security=settings), auth=auth,
                                          tts_jobs=jobs, asr_jobs=jobs, production=projects)
    app.include_router(tts_router, prefix="/api/v1/tts")
    app.include_router(asr_router, prefix="/api/v1/asr")
    return SimpleNamespace(client=TestClient(app, headers={"X-Vassil-API-Key": token}), jobs=jobs,
                           projects=projects, owner=owner["principal_id"], settings=settings, app=app)


def test_tts_actor_acl_covers_list_audio_read_mutations_and_cleanup(env):
    client = env.client
    assert [item["job_id"] for item in client.get("/api/v1/tts/jobs?limit=1").json()] == ["own"]
    owned = client.get("/api/v1/tts/jobs/own").json()
    assert owned["actor_id"] == env.owner and owned["request_id"] == "trace"
    assert owned["recovery_count"] == 1
    for job_id in ("foreign", "legacy", "project"):
        for method, suffix in (("get", ""), ("get", "/audio"), ("post", "/cancel"),
                                ("post", "/retry"), ("delete", "")):
            assert getattr(client, method)(f"/api/v1/tts/jobs/{job_id}{suffix}").status_code == 404
    assert env.jobs.mutations == []
    assert client.get("/api/v1/tts/jobs/own/audio").content == b"test-audio"
    assert client.delete("/api/v1/tts/jobs").json()["job_ids"] == ["own"]
    assert env.jobs.mutations == [("delete", "own")]
    assert len(client.get("/api/v1/tts/jobs", headers={"X-Vassil-API-Key": "admin-key"}).json()) == 4


def test_production_job_access_requires_live_project_acl_even_for_original_actor(env):
    env.projects.allowed[("private-project", env.owner)] = {"read"}
    assert env.client.get("/api/v1/tts/jobs/project/audio").status_code == 200
    assert env.client.post("/api/v1/tts/jobs/project/cancel").status_code == 404
    env.projects.allowed[("private-project", env.owner)] = {"read", "write"}
    assert env.client.post("/api/v1/tts/jobs/project/cancel").status_code == 200
    assert env.client.post("/api/v1/tts/jobs/project/retry").status_code == 409
    assert ("retry", "project") not in env.jobs.mutations
    env.projects.allowed.clear()
    assert env.client.get("/api/v1/tts/jobs/project").status_code == 404


def test_asr_actor_acl_covers_transcript_audio_read_delete_and_cleanup(env):
    # ASR has no project association; only the owning actor or administrator can read it.
    assert [item["job_id"] for item in env.client.get("/api/v1/asr/jobs?limit=1").json()] == ["own"]
    for job_id in ("foreign", "legacy"):
        for method, suffix in (("get", ""), ("get", "/audio"), ("get", "/exports/txt"),
                                ("post", "/cancel"), ("delete", "")):
            assert getattr(env.client, method)(f"/api/v1/asr/jobs/{job_id}{suffix}").status_code == 404
        assert env.client.patch(f"/api/v1/asr/jobs/{job_id}/transcript",
                                json={"expected_revision": 0, "text": "Changed"}).status_code == 404
    assert env.jobs.mutations == []
    assert env.client.get("/api/v1/asr/jobs/own/exports/txt").text == "Example\n"
    assert set(env.client.delete("/api/v1/asr/jobs").json()["job_ids"]) == {"own", "project"}
    assert len(env.client.get("/api/v1/asr/jobs", headers={"X-Vassil-API-Key": "admin-key"}).json()) == 4


def test_read_only_key_cannot_mutate_own_jobs(env):
    account = env.app.state.container.auth.create_service_account("reader", "reviewer")
    token = env.app.state.container.auth.create_api_key(account["principal_id"], "review")["token"]
    env.jobs.jobs["own"].actor_id = account["principal_id"]
    headers = {"X-Vassil-API-Key": token}
    assert env.client.get("/api/v1/tts/jobs/own", headers=headers).status_code == 200
    assert env.client.post("/api/v1/tts/jobs/own/cancel", headers=headers).status_code == 403
    assert env.client.delete("/api/v1/asr/jobs/own", headers=headers).status_code == 403
