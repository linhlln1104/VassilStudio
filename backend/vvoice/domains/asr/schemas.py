from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TranscriptionResponse(BaseModel):
    text: str
    sample_rate: int
    duration_seconds: float


class AsrJobResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    language: str
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
    text: str | None
    sample_rate: int | None
    duration_seconds: float | None
    audio_url: str | None


class AsrJobCleanupResponse(BaseModel):
    deleted: int
    job_ids: list[str]


class AsrJobDeleteResponse(BaseModel):
    deleted: bool
    job_id: str
