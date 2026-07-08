from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    asr_enabled: bool
    tts_enabled: bool
    provider: str
    asr_loaded: bool
    tts_loaded: bool


class ProbeResponse(BaseModel):
    status: str
    checks: dict[str, bool]


class DiagnosticsStorageItem(BaseModel):
    name: str
    path: str
    exists: bool
    is_dir: bool
    size_bytes: int
    file_count: int


class DiagnosticsSecurity(BaseModel):
    auth_required: bool
    api_key_auth_enabled: bool
    session_cookie_name: str
    session_ttl_seconds: int
    secure_cookies: bool


class DiagnosticsLicense(BaseModel):
    status: str
    plan: str
    billing_enabled: bool


class RuntimeStatus(BaseModel):
    provider: str
    num_threads: int
    debug: bool
    warmup_on_startup: bool
    asr_job_workers: int
    tts_job_workers: int
    asr_job_max_attempts: int
    tts_job_max_attempts: int
    job_retry_backoff_seconds: float
    asr_loaded: bool
    tts_loaded: bool
    asr_configured_languages: list[str]
    asr_loaded_languages: list[str]
    tts_configured_languages: list[str]
    tts_loaded_languages: list[str]


class ModelStatusResponse(BaseModel):
    ready: bool
    checks: dict[str, bool]
    runtime: RuntimeStatus


class DiagnosticsResponse(BaseModel):
    generated_at: str
    runtime: RuntimeStatus
    security: DiagnosticsSecurity
    storage: list[DiagnosticsStorageItem]
    license: DiagnosticsLicense


class WarmupResponse(BaseModel):
    loaded: bool
    loaded_languages: list[str]


class WarmupAllResponse(BaseModel):
    asr_loaded: bool
    tts_loaded: bool
    asr_loaded_languages: list[str]
    tts_loaded_languages: list[str]
