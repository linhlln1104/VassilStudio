from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class VoiceResponse(BaseModel):
    voice_id: str
    name: str
    language: str
    reference_text: str
    reference_text_source: str
    audio_size_bytes: int
    sample_rate: int
    duration_seconds: float
    created_at: str
    updated_at: str | None
    reference_audio_url: str


class VoiceImportCandidateResponse(BaseModel):
    filename: str
    name: str
    size_bytes: int
    updated_at: float
    audio_url: str


class VoiceIntakeIssueResponse(BaseModel):
    code: str
    severity: Literal["warning", "blocking"]
    message: str


class VoiceIntakeDuplicateResponse(BaseModel):
    voice_id: str
    name: str
    language: str


class VoiceIntakeReportResponse(BaseModel):
    status: Literal["ready", "review", "blocked"]
    can_create: bool
    source_sha256: str
    audio_sha256: str
    source_duration_seconds: float
    duration_seconds: float
    source_sample_rate: int
    target_sample_rate: int
    channels: int
    trim_start_seconds: float
    trim_end_seconds: float
    suggested_trim_start_seconds: float
    suggested_trim_end_seconds: float
    leading_silence_seconds: float
    trailing_silence_seconds: float
    clipping_ratio: float
    speech_coverage_ratio: float
    peak_amplitude: float
    reference_text: str
    reference_text_source: Literal["user", "asr", "none"]
    issues: list[VoiceIntakeIssueResponse]
    duplicate: VoiceIntakeDuplicateResponse | None


class VoiceDeleteResponse(BaseModel):
    deleted: bool
    voice_id: str
