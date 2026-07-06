from __future__ import annotations

from pydantic import BaseModel


class VoiceResponse(BaseModel):
    voice_id: str
    name: str
    language: str
    reference_text: str
    reference_text_source: str
    audio_path: str
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


class VoiceDeleteResponse(BaseModel):
    deleted: bool
    voice_id: str
