from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TranscriptSegmentResponse(BaseModel):
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str


class TranscriptSegmentEdit(BaseModel):
    segment_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2_000)


class TranscriptRevisionRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    text: str | None = Field(default=None, min_length=1, max_length=100_000)
    segments: list[TranscriptSegmentEdit] | None = Field(default=None, max_length=5_000)

    @model_validator(mode="after")
    def validate_revision_mode(self):
        if (self.text is None) == (self.segments is None):
            raise ValueError("Provide either text or segments")
        return self


class TranscriptionResponse(BaseModel):
    text: str
    sample_rate: int
    duration_seconds: float
    timing_status: Literal["available", "unavailable"]
    segments: list[TranscriptSegmentResponse]


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
    raw_text: str | None
    raw_segments: list[TranscriptSegmentResponse]
    segments: list[TranscriptSegmentResponse]
    timing_status: Literal["available", "unavailable"]
    transcript_revision: int
    transcript_edited: bool
    transcript_updated_at: str | None


class AsrJobCleanupResponse(BaseModel):
    deleted: int
    job_ids: list[str]


class AsrJobDeleteResponse(BaseModel):
    deleted: bool
    job_id: str
