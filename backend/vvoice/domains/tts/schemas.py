from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TtsModelCapabilitiesResponse(BaseModel):
    reference_audio: bool
    num_steps: bool
    speed: bool


class TtsModelResponse(BaseModel):
    model_id: str
    engine: str
    label: str
    languages: list[str]
    sample_rate: int
    capabilities: TtsModelCapabilitiesResponse
    ready: bool
    loaded: bool
    status: str
    checks: dict[str, bool]
    message: str | None


class TtsModelCatalogResponse(BaseModel):
    default_models: dict[str, str]
    models: list[TtsModelResponse]


class TtsJobResponse(BaseModel):
    job_id: str
    status: str
    voice_id: str
    language: str
    model_id: str
    text: str
    num_steps: int | None
    speed: float | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    error: str | None
    attempt: int
    max_attempts: int
    cancel_requested: bool
    cancellation_mode: Literal["safe_point"]
    failed_reason: str | None
    progress_stage: Literal[
        "queued",
        "preparing_input",
        "running_model",
        "finalizing",
        "retry_wait",
        "succeeded",
        "failed",
        "cancelled",
    ]
    stage_started_at: str
    sample_rate: int | None
    duration_seconds: float | None
    audio_url: str | None
    actor_id: str | None = None
    request_id: str | None = None
    provenance: dict = Field(default_factory=dict)
    recovery_count: int = 0


class TtsJobCleanupResponse(BaseModel):
    deleted: int
    job_ids: list[str]


class TtsJobDeleteResponse(BaseModel):
    deleted: bool
    job_id: str
