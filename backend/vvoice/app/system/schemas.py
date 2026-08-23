from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
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
    path_alias: str
    exists: bool
    is_dir: bool
    writable: bool
    usage_bucket: Literal[
        "empty",
        "under_1_mb",
        "1_to_99_mb",
        "100_to_999_mb",
        "1_to_9_gb",
        "10_to_99_gb",
        "100_gb_or_more",
    ]
    file_count_bucket: Literal["none", "1_to_9", "10_to_99", "100_to_999", "1000_or_more"]
    capacity_bucket: Literal[
        "under_10_gb",
        "10_to_49_gb",
        "50_to_99_gb",
        "100_to_499_gb",
        "500_to_999_gb",
        "1_tb_or_more",
    ] | None
    free_space_bucket: Literal[
        "under_10_gb",
        "10_to_49_gb",
        "50_to_99_gb",
        "100_to_499_gb",
        "500_to_999_gb",
        "1_tb_or_more",
    ] | None
    storage_pressure: Literal["normal", "low", "critical", "unknown"]


class DiagnosticsPrivacy(BaseModel):
    storage_paths: Literal["logical_aliases"]
    storage_metrics: Literal["bucketed"]
    host_metadata_included: bool


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
    environment: str
    log_level: str
    provider: str
    num_threads: int
    asr_num_threads: int
    tts_num_threads: int
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
    version: str
    privacy: DiagnosticsPrivacy
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
