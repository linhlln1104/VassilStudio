from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    asr_enabled: bool
    tts_enabled: bool
    provider: str
    asr_loaded: bool
    tts_loaded: bool


class RuntimeStatus(BaseModel):
    provider: str
    num_threads: int
    debug: bool
    asr_job_workers: int
    tts_job_workers: int
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


class WarmupResponse(BaseModel):
    loaded: bool
    loaded_languages: list[str]


class WarmupAllResponse(BaseModel):
    asr_loaded: bool
    tts_loaded: bool
    asr_loaded_languages: list[str]
    tts_loaded_languages: list[str]
