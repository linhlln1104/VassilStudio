from __future__ import annotations

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
