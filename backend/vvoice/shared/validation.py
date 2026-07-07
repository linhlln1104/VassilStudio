from __future__ import annotations

from pathlib import Path, PureWindowsPath

from fastapi import UploadFile

from vvoice.core.errors import VVoiceError


UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


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
