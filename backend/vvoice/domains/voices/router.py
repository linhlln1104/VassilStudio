from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from vvoice.core.errors import VVoiceError
from vvoice.domains.voices.schemas import (
    VoiceDeleteResponse,
    VoiceImportCandidateResponse,
    VoiceResponse,
)
from vvoice.shared.audio.io import duration_seconds, encode_wav, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.shared.validation import (
    ensure_file_size,
    read_audio_upload,
    validate_audio_bytes,
    validate_text_field,
)


router = APIRouter()

AUDIO_MEDIA_TYPES = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".weba": "audio/webm",
    ".webm": "audio/webm",
}


@router.get("", response_model=list[VoiceResponse])
async def list_voices(request: Request):
    container = request.app.state.container
    return [_voice_response(voice) for voice in container.voices.list()]


@router.get("/import-candidates", response_model=list[VoiceImportCandidateResponse])
async def list_voice_import_candidates(request: Request):
    container = request.app.state.container
    return [_import_candidate_response(path) for path in container.voices.list_import_candidates()]


@router.get("/import-candidates/{filename}/audio")
async def get_voice_import_candidate_audio(request: Request, filename: str):
    container = request.app.state.container
    audio_path = container.voices.import_candidate_path(filename)
    return FileResponse(
        audio_path,
        media_type=_audio_media_type(audio_path),
        filename=audio_path.name,
    )


@router.post("/import", response_model=VoiceResponse)
async def import_voice(
    request: Request,
    filename: str = Form(...),
    name: str | None = Form(default=None),
    language: str = Form(default=DEFAULT_LANGUAGE),
    reference_text: str | None = Form(default=None),
    auto_transcribe: bool = Form(default=True),
):
    container = request.app.state.container
    audio_path = container.voices.import_candidate_path(filename)
    ensure_file_size(
        audio_path,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="reference_audio",
    )
    raw_audio = audio_path.read_bytes()
    validate_audio_bytes(
        raw_audio,
        filename=audio_path.name,
        content_type=_audio_media_type(audio_path),
        field_name="reference_audio",
    )
    profile = await _create_voice_from_audio(
        request,
        raw_audio=raw_audio,
        name=(name or audio_path.stem).strip(),
        language=language,
        reference_text=reference_text,
        auto_transcribe=auto_transcribe,
    )
    return _voice_response(profile)


@router.get("/{voice_id}", response_model=VoiceResponse)
async def get_voice(request: Request, voice_id: str):
    container = request.app.state.container
    profile = container.voices.get(voice_id)
    return _voice_response(profile)


@router.get("/{voice_id}/reference-audio")
async def get_voice_reference_audio(request: Request, voice_id: str):
    container = request.app.state.container
    profile = container.voices.get(voice_id)
    return FileResponse(
        profile.audio_path,
        media_type="audio/wav",
        filename=f"{profile.voice_id}-reference.wav",
    )


@router.post("", response_model=VoiceResponse)
async def create_voice(
    request: Request,
    name: str = Form(...),
    language: str = Form(default=DEFAULT_LANGUAGE),
    reference_text: str | None = Form(default=None),
    auto_transcribe: bool = Form(default=False),
    reference_audio: UploadFile = File(...),
):
    container = request.app.state.container
    raw_audio = await read_audio_upload(
        reference_audio,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="reference_audio",
    )
    profile = await _create_voice_from_audio(
        request,
        raw_audio=raw_audio,
        name=name,
        language=language,
        reference_text=reference_text,
        auto_transcribe=auto_transcribe,
    )
    return _voice_response(profile)


@router.patch("/{voice_id}", response_model=VoiceResponse)
async def update_voice(
    request: Request,
    voice_id: str,
    name: str | None = Form(default=None),
    language: str | None = Form(default=None),
    reference_text: str | None = Form(default=None),
):
    container = request.app.state.container
    normalized_name = (
        validate_text_field(
            name,
            field_name="name",
            max_chars=container.settings.limits.max_voice_name_chars,
        )
        if name is not None
        else None
    )
    normalized_language = normalize_language(language) if language is not None else None
    normalized_reference_text = (
        validate_text_field(
            reference_text,
            field_name="reference_text",
            max_chars=container.settings.limits.max_reference_text_chars,
        )
        if reference_text is not None
        else None
    )

    if normalized_name is None and normalized_language is None and normalized_reference_text is None:
        raise VVoiceError("Provide name, language, or reference_text to update")
    if normalized_language is not None:
        container.tts.sample_rate_for(normalized_language)

    profile = container.voices.update(
        voice_id,
        name=normalized_name,
        language=normalized_language,
        reference_text=normalized_reference_text,
    )
    return _voice_response(profile)


@router.delete("/{voice_id}", response_model=VoiceDeleteResponse)
async def delete_voice(request: Request, voice_id: str):
    container = request.app.state.container
    container.voices.delete(voice_id)
    return {"deleted": True, "voice_id": voice_id}


def _voice_response(profile):
    return {
        "voice_id": profile.voice_id,
        "name": profile.name,
        "language": profile.language,
        "reference_text": profile.reference_text,
        "reference_text_source": profile.reference_text_source,
        "audio_size_bytes": profile.audio_size_bytes,
        "sample_rate": profile.sample_rate,
        "duration_seconds": profile.duration_seconds,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "reference_audio_url": f"/api/v1/voices/{profile.voice_id}/reference-audio",
    }


async def _create_voice_from_audio(
    request: Request,
    *,
    raw_audio: bytes,
    name: str,
    language: str,
    reference_text: str | None,
    auto_transcribe: bool,
):
    container = request.app.state.container
    normalized_name = validate_text_field(
        name,
        field_name="name",
        max_chars=container.settings.limits.max_voice_name_chars,
    )
    assert normalized_name is not None
    normalized_language = normalize_language(language)

    final_reference_text = validate_text_field(
        reference_text,
        field_name="reference_text",
        max_chars=container.settings.limits.max_reference_text_chars,
        required=False,
    )
    reference_text_source = "user"

    if auto_transcribe or not final_reference_text:
        asr_samples, asr_sample_rate = await run_in_threadpool(
            load_audio_bytes,
            raw_audio,
            container.asr.sample_rate_for(normalized_language),
        )
        transcription = await run_in_threadpool(
            container.asr.transcribe,
            asr_samples,
            asr_sample_rate,
            normalized_language,
        )
        final_reference_text = validate_text_field(
            transcription.text,
            field_name="reference_text",
            max_chars=container.settings.limits.max_reference_text_chars,
            required=False,
        )
        reference_text_source = "asr"

    if not final_reference_text:
        raise VVoiceError(
            "reference_text is required. Provide it manually or use clearer reference audio "
            "with auto_transcribe=true."
        )

    samples, sample_rate = await run_in_threadpool(
        load_audio_bytes,
        raw_audio,
        container.tts.sample_rate_for(normalized_language),
    )
    audio_bytes = encode_wav(samples, sample_rate)
    return container.voices.create(
        name=normalized_name,
        language=normalized_language,
        reference_text=final_reference_text,
        reference_text_source=reference_text_source,
        audio_bytes=audio_bytes,
        sample_rate=sample_rate,
        duration_seconds=duration_seconds(samples, sample_rate),
    )


def _import_candidate_response(path):
    stat = path.stat()
    return {
        "filename": path.name,
        "name": path.stem,
        "size_bytes": stat.st_size,
        "updated_at": stat.st_mtime,
        "audio_url": f"/api/v1/voices/import-candidates/{quote(path.name)}/audio",
    }


def _audio_media_type(path: Path) -> str:
    return AUDIO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
