from __future__ import annotations

from pathlib import Path, PureWindowsPath

from fastapi import UploadFile

from vvoice.core.errors import UnsupportedAudioFormatError, VVoiceError


UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".weba", ".webm"}
)
GENERIC_UPLOAD_MEDIA_TYPES = frozenset({"application/octet-stream"})
AUDIO_MEDIA_TYPES_BY_EXTENSION = {
    ".flac": frozenset({"audio/flac", "audio/x-flac"}),
    ".m4a": frozenset({"audio/mp4", "audio/x-m4a", "video/mp4"}),
    ".mp3": frozenset({"audio/mp3", "audio/mpeg"}),
    ".ogg": frozenset({"application/ogg", "audio/ogg"}),
    ".opus": frozenset({"application/ogg", "audio/ogg", "audio/opus"}),
    ".wav": frozenset({"audio/vnd.wave", "audio/wav", "audio/wave", "audio/x-wav"}),
    ".weba": frozenset({"audio/webm", "video/webm"}),
    ".webm": frozenset({"audio/webm", "video/webm"}),
}


async def read_upload_file(
    upload: UploadFile,
    *,
    max_bytes: int,
    field_name: str = "upload",
) -> bytes:
    total = 0
    chunks: list[bytes] = []

    while True:
        chunk = await upload.read(UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break

        total += len(chunk)
        if total > max_bytes:
            raise VVoiceError(
                f"{field_name} exceeds the maximum size of {_format_bytes(max_bytes)}"
            )
        chunks.append(chunk)

    if total == 0:
        raise VVoiceError(f"{field_name} cannot be empty")

    return b"".join(chunks)


async def read_audio_upload(
    upload: UploadFile,
    *,
    max_bytes: int,
    field_name: str = "audio",
) -> bytes:
    data = await read_upload_file(upload, max_bytes=max_bytes, field_name=field_name)
    validate_audio_bytes(
        data,
        filename=upload.filename,
        content_type=upload.content_type,
        field_name=field_name,
    )
    return data


def validate_audio_bytes(
    data: bytes,
    *,
    filename: str | None,
    content_type: str | None,
    field_name: str = "audio",
) -> None:
    extension = Path(safe_display_filename(filename, fallback="")).suffix.lower()
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise _unsupported_audio_format(field_name)

    normalized_content_type = (content_type or "").partition(";")[0].strip().lower()
    allowed_media_types = AUDIO_MEDIA_TYPES_BY_EXTENSION[extension]
    if normalized_content_type and normalized_content_type not in (
        allowed_media_types | GENERIC_UPLOAD_MEDIA_TYPES
    ):
        raise _unsupported_audio_format(field_name)

    if not _matches_audio_signature(data, extension):
        raise _unsupported_audio_format(field_name)


def validate_text_field(
    value: str | None,
    *,
    field_name: str,
    max_chars: int,
    required: bool = True,
) -> str | None:
    if value is None:
        if required:
            raise VVoiceError(f"{field_name} is required")
        return None

    normalized = value.strip()
    if not normalized:
        if required:
            raise VVoiceError(f"{field_name} cannot be empty")
        return None

    if len(normalized) > max_chars:
        raise VVoiceError(
            f"{field_name} must be {max_chars} characters or fewer"
        )

    return normalized


def safe_display_filename(value: str | None, *, fallback: str = "audio") -> str:
    raw = (value or fallback).strip()
    filename = Path(PureWindowsPath(raw).name).name.strip()
    return filename if filename and filename not in {".", ".."} else fallback


def ensure_file_size(path: Path, *, max_bytes: int, field_name: str) -> None:
    size = path.stat().st_size
    if size == 0:
        raise VVoiceError(f"{field_name} cannot be empty")
    if size > max_bytes:
        raise VVoiceError(
            f"{field_name} exceeds the maximum size of {_format_bytes(max_bytes)}"
        )


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.0f} MB"
    if value >= 1024:
        return f"{value / 1024:.0f} KB"
    return f"{value} bytes"


def _matches_audio_signature(data: bytes, extension: str) -> bool:
    if extension == ".wav":
        return len(data) >= 12 and data[:4] in {b"RIFF", b"RF64"} and data[8:12] == b"WAVE"
    if extension == ".flac":
        return data.startswith(b"fLaC")
    if extension in {".ogg", ".opus"}:
        return data.startswith(b"OggS")
    if extension == ".mp3":
        return data.startswith(b"ID3") or (
            len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
        )
    if extension in {".weba", ".webm"}:
        return data.startswith(b"\x1aE\xdf\xa3")
    if extension == ".m4a":
        return len(data) >= 12 and data[4:8] == b"ftyp"
    return False


def _unsupported_audio_format(field_name: str) -> UnsupportedAudioFormatError:
    return UnsupportedAudioFormatError(
        f"{field_name} must be a valid WAV, MP3, WebM, FLAC, M4A, OGG, or Opus file"
    )
