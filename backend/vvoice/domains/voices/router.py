from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from vvoice.core.errors import (
    VVoiceError,
    VoiceDuplicateError,
    VoiceIntakeConflictError,
    VoiceIntakeRejectedError,
)
from vvoice.domains.voices.intake import (
    VoiceIntakeIssue,
    intake_status,
    prepare_voice_audio,
    reference_text_issues,
)
from vvoice.domains.voices.schemas import (
    VoiceDeleteResponse,
    VoiceImportCandidateResponse,
    VoiceIntakeReportResponse,
    VoiceResponse,
)
from vvoice.shared.audio.io import load_audio_bytes
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


@router.post("/intake/analyze", response_model=VoiceIntakeReportResponse)
async def analyze_voice_upload(
    request: Request,
    language: str = Form(default=DEFAULT_LANGUAGE),
    reference_text: str | None = Form(default=None),
    auto_transcribe: bool = Form(default=False),
    trim_start_seconds: float = Form(default=0.0),
    trim_end_seconds: float | None = Form(default=None),
    reference_audio: UploadFile = File(...),
):
    container = request.app.state.container
    raw_audio = await read_audio_upload(
        reference_audio,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="reference_audio",
    )
    return await _analyze_voice_intake(
        request,
        raw_audio=raw_audio,
        language=language,
        reference_text=reference_text,
        auto_transcribe=auto_transcribe,
        trim_start_seconds=trim_start_seconds,
        trim_end_seconds=trim_end_seconds,
    )


@router.post(
    "/import-candidates/{filename}/analyze",
    response_model=VoiceIntakeReportResponse,
)
async def analyze_voice_import_candidate(
    request: Request,
    filename: str,
    language: str = Form(default=DEFAULT_LANGUAGE),
    reference_text: str | None = Form(default=None),
    auto_transcribe: bool = Form(default=False),
    trim_start_seconds: float = Form(default=0.0),
    trim_end_seconds: float | None = Form(default=None),
):
    container = request.app.state.container
    _, raw_audio = await run_in_threadpool(_read_import_candidate, container, filename)
    return await _analyze_voice_intake(
        request,
        raw_audio=raw_audio,
        language=language,
        reference_text=reference_text,
        auto_transcribe=auto_transcribe,
        trim_start_seconds=trim_start_seconds,
        trim_end_seconds=trim_end_seconds,
    )


@router.post("/import", response_model=VoiceResponse)
async def import_voice(
    request: Request,
    filename: str = Form(...),
    name: str | None = Form(default=None),
    language: str = Form(default=DEFAULT_LANGUAGE),
    reference_text: str | None = Form(default=None),
    auto_transcribe: bool = Form(default=True),
    trim_start_seconds: float = Form(default=0.0),
    trim_end_seconds: float | None = Form(default=None),
    reviewed_source_sha256: str | None = Form(default=None),
    acknowledge_warnings: bool = Form(default=False),
):
    container = request.app.state.container
    audio_path, raw_audio = await run_in_threadpool(
        _read_import_candidate,
        container,
        filename,
    )
    profile = await _create_voice_from_audio(
        request,
        raw_audio=raw_audio,
        name=(name or audio_path.stem).strip(),
        language=language,
        reference_text=reference_text,
        auto_transcribe=auto_transcribe,
        trim_start_seconds=trim_start_seconds,
        trim_end_seconds=trim_end_seconds,
        reviewed_source_sha256=reviewed_source_sha256,
        acknowledge_warnings=acknowledge_warnings,
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
    trim_start_seconds: float = Form(default=0.0),
    trim_end_seconds: float | None = Form(default=None),
    reviewed_source_sha256: str | None = Form(default=None),
    acknowledge_warnings: bool = Form(default=False),
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
        trim_start_seconds=trim_start_seconds,
        trim_end_seconds=trim_end_seconds,
        reviewed_source_sha256=reviewed_source_sha256,
        acknowledge_warnings=acknowledge_warnings,
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
    if normalized_language is not None or normalized_reference_text is not None:
        current = container.voices.get(voice_id)
        text_issues = reference_text_issues(
            normalized_reference_text or current.reference_text,
            normalized_language or current.language,
        )
        blocking_messages = [
            issue.message for issue in text_issues if issue.severity == "blocking"
        ]
        if blocking_messages:
            raise VoiceIntakeRejectedError(
                "Voice profile update was rejected: " + " ".join(blocking_messages)
            )

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
    trim_start_seconds: float = 0.0,
    trim_end_seconds: float | None = None,
    reviewed_source_sha256: str | None = None,
    acknowledge_warnings: bool = False,
):
    container = request.app.state.container
    normalized_name = validate_text_field(
        name,
        field_name="name",
        max_chars=container.settings.limits.max_voice_name_chars,
    )
    assert normalized_name is not None
    normalized_language = normalize_language(language)
    prepared = await run_in_threadpool(
        prepare_voice_audio,
        raw_audio,
        target_sample_rate=container.tts.sample_rate_for(normalized_language),
        trim_start_seconds=trim_start_seconds,
        trim_end_seconds=trim_end_seconds,
    )
    if reviewed_source_sha256 is not None:
        reviewed_hash = reviewed_source_sha256.strip().lower()
        if reviewed_hash != prepared.source_sha256:
            raise VoiceIntakeConflictError(
                "The source audio changed after review. Analyze it again before creating the profile."
            )

    duplicate = await run_in_threadpool(
        container.voices.find_by_audio_sha256,
        prepared.audio_sha256,
    )
    if duplicate is not None:
        raise VoiceDuplicateError(
            f'Audio already belongs to voice profile "{duplicate.name}". '
            "Reuse that profile instead of creating a duplicate."
        )

    audio_blocking_messages = [
        issue.message for issue in prepared.issues if issue.severity == "blocking"
    ]
    if audio_blocking_messages:
        raise VoiceIntakeRejectedError(
            "Voice intake was rejected: " + " ".join(audio_blocking_messages)
        )

    final_reference_text = validate_text_field(
        reference_text,
        field_name="reference_text",
        max_chars=container.settings.limits.max_reference_text_chars,
        required=False,
    )
    reference_text_source = "user"

    if auto_transcribe or not final_reference_text:
        final_reference_text = await _transcribe_reference_audio(
            request,
            raw_audio=raw_audio,
            language=normalized_language,
            trim_start_seconds=prepared.trim_start_seconds,
            trim_end_seconds=prepared.trim_end_seconds,
        )
        final_reference_text = validate_text_field(
            final_reference_text,
            field_name="reference_text",
            max_chars=container.settings.limits.max_reference_text_chars,
            required=False,
        )
        reference_text_source = "asr"

    issues = (*prepared.issues, *reference_text_issues(final_reference_text, normalized_language))
    blocking_messages = [issue.message for issue in issues if issue.severity == "blocking"]
    if blocking_messages:
        raise VoiceIntakeRejectedError("Voice intake was rejected: " + " ".join(blocking_messages))
    if reviewed_source_sha256 is not None and issues and not acknowledge_warnings:
        raise VoiceIntakeConflictError(
            "Voice intake warnings must be acknowledged after review before creating the profile."
        )

    return await run_in_threadpool(
        container.voices.create,
        name=normalized_name,
        language=normalized_language,
        reference_text=final_reference_text,
        reference_text_source=reference_text_source,
        audio_bytes=prepared.audio_bytes,
        audio_sha256=prepared.audio_sha256,
        sample_rate=prepared.target_sample_rate,
        duration_seconds=prepared.duration_seconds,
    )


async def _analyze_voice_intake(
    request: Request,
    *,
    raw_audio: bytes,
    language: str,
    reference_text: str | None,
    auto_transcribe: bool,
    trim_start_seconds: float,
    trim_end_seconds: float | None,
):
    container = request.app.state.container
    normalized_language = normalize_language(language)
    normalized_reference_text = validate_text_field(
        reference_text,
        field_name="reference_text",
        max_chars=container.settings.limits.max_reference_text_chars,
        required=False,
    )
    reference_text_source = "user" if normalized_reference_text else "none"
    prepared = await run_in_threadpool(
        prepare_voice_audio,
        raw_audio,
        target_sample_rate=container.tts.sample_rate_for(normalized_language),
        trim_start_seconds=trim_start_seconds,
        trim_end_seconds=trim_end_seconds,
    )
    duplicate = await run_in_threadpool(
        container.voices.find_by_audio_sha256,
        prepared.audio_sha256,
    )
    audio_is_blocked = any(issue.severity == "blocking" for issue in prepared.issues)

    if auto_transcribe and duplicate is None and not audio_is_blocked:
        normalized_reference_text = await _transcribe_reference_audio(
            request,
            raw_audio=raw_audio,
            language=normalized_language,
            trim_start_seconds=prepared.trim_start_seconds,
            trim_end_seconds=prepared.trim_end_seconds,
        )
        normalized_reference_text = validate_text_field(
            normalized_reference_text,
            field_name="reference_text",
            max_chars=container.settings.limits.max_reference_text_chars,
            required=False,
        )
        reference_text_source = "asr"

    issues = [*prepared.issues, *reference_text_issues(normalized_reference_text, normalized_language)]
    if duplicate is not None:
        issues.append(
            VoiceIntakeIssue(
                code="duplicate_audio",
                severity="blocking",
                message=f'This audio already belongs to voice profile "{duplicate.name}". Reuse it instead.',
            )
        )
    status = intake_status(issues)
    return {
        "status": status,
        "can_create": status != "blocked",
        "source_sha256": prepared.source_sha256,
        "audio_sha256": prepared.audio_sha256,
        "source_duration_seconds": prepared.source_duration_seconds,
        "duration_seconds": prepared.duration_seconds,
        "source_sample_rate": prepared.source_sample_rate,
        "target_sample_rate": prepared.target_sample_rate,
        "channels": prepared.channels,
        "trim_start_seconds": prepared.trim_start_seconds,
        "trim_end_seconds": prepared.trim_end_seconds,
        "suggested_trim_start_seconds": prepared.suggested_trim_start_seconds,
        "suggested_trim_end_seconds": prepared.suggested_trim_end_seconds,
        "leading_silence_seconds": prepared.metrics.leading_silence_seconds,
        "trailing_silence_seconds": prepared.metrics.trailing_silence_seconds,
        "clipping_ratio": prepared.metrics.clipping_ratio,
        "speech_coverage_ratio": prepared.metrics.speech_coverage_ratio,
        "peak_amplitude": prepared.metrics.peak_amplitude,
        "reference_text": normalized_reference_text or "",
        "reference_text_source": reference_text_source,
        "issues": [
            {"code": issue.code, "severity": issue.severity, "message": issue.message}
            for issue in issues
        ],
        "duplicate": (
            {
                "voice_id": duplicate.voice_id,
                "name": duplicate.name,
                "language": duplicate.language,
            }
            if duplicate is not None
            else None
        ),
    }


async def _transcribe_reference_audio(
    request: Request,
    *,
    raw_audio: bytes,
    language: str,
    trim_start_seconds: float,
    trim_end_seconds: float,
) -> str:
    container = request.app.state.container
    asr_samples, asr_sample_rate = await run_in_threadpool(
        load_audio_bytes,
        raw_audio,
        container.asr.sample_rate_for(language),
    )
    start_index = min(len(asr_samples), round(trim_start_seconds * asr_sample_rate))
    end_index = min(len(asr_samples), round(trim_end_seconds * asr_sample_rate))
    selected_samples = asr_samples[start_index:end_index]
    if selected_samples.size == 0:
        raise VoiceIntakeRejectedError("The selected trim range contains no audio samples")
    transcription = await run_in_threadpool(
        container.asr.transcribe,
        selected_samples,
        asr_sample_rate,
        language,
    )
    return transcription.text


def _read_import_candidate(container, filename: str) -> tuple[Path, bytes]:
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
    return audio_path, raw_audio


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
