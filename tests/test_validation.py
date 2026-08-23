import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from vvoice.core.errors import UnsupportedAudioFormatError, VVoiceError
from vvoice.shared.validation import (
    read_audio_upload,
    read_upload_file,
    safe_display_filename,
    validate_audio_bytes,
    validate_text_field,
)


def test_validate_text_field_strips_and_limits() -> None:
    assert validate_text_field("  hello  ", field_name="text", max_chars=8) == "hello"

    with pytest.raises(VVoiceError, match="text must be 4 characters or fewer"):
        validate_text_field("hello", field_name="text", max_chars=4)


def test_validate_optional_text_field_returns_none_for_blank() -> None:
    assert validate_text_field("", field_name="reference_text", max_chars=8, required=False) is None


def test_safe_display_filename_removes_path_segments() -> None:
    assert safe_display_filename("../folder/input.wav") == "input.wav"
    assert safe_display_filename(r"C:\recordings\input.wav") == "input.wav"
    assert safe_display_filename("", fallback="audio") == "audio"


def test_read_upload_file_rejects_empty_and_oversized_uploads() -> None:
    empty = UploadFile(file=BytesIO(b""), filename="empty.wav")
    with pytest.raises(VVoiceError, match="audio cannot be empty"):
        asyncio.run(read_upload_file(empty, max_bytes=8, field_name="audio"))

    oversized = UploadFile(file=BytesIO(b"123456789"), filename="input.wav")
    with pytest.raises(VVoiceError, match="audio exceeds the maximum size"):
        asyncio.run(read_upload_file(oversized, max_bytes=8, field_name="audio"))


def test_read_upload_file_returns_bytes_within_limit() -> None:
    upload = UploadFile(file=BytesIO(b"audio"), filename="input.wav")

    data = asyncio.run(read_upload_file(upload, max_bytes=8, field_name="audio"))

    assert data == b"audio"


@pytest.mark.parametrize(
    ("filename", "content_type", "data"),
    [
        ("input.wav", "audio/wav", b"RIFF\x04\x00\x00\x00WAVE"),
        ("input.mp3", "audio/mpeg", b"ID3\x04\x00\x00"),
        ("input.webm", "video/webm", b"\x1aE\xdf\xa3\x01"),
        ("input.weba", "audio/webm; codecs=opus", b"\x1aE\xdf\xa3\x01"),
        ("input.flac", "audio/flac", b"fLaC\x00"),
        ("input.m4a", "audio/mp4", b"\x00\x00\x00\x18ftypM4A "),
        ("input.ogg", "audio/ogg", b"OggS\x00"),
        ("input.opus", "audio/opus", b"OggS\x00"),
    ],
)
def test_validate_audio_bytes_accepts_supported_container_signatures(
    filename,
    content_type,
    data,
) -> None:
    validate_audio_bytes(data, filename=filename, content_type=content_type)


@pytest.mark.parametrize(
    ("filename", "content_type", "data"),
    [
        ("notes.txt", "audio/wav", b"RIFF\x04\x00\x00\x00WAVE"),
        ("input.wav", "text/plain", b"RIFF\x04\x00\x00\x00WAVE"),
        ("input.wav", "audio/wav", b"not-a-wave-file"),
        ("input.mp3", "audio/mpeg", b"not-an-mp3-file"),
    ],
)
def test_validate_audio_bytes_rejects_extension_mime_or_signature_mismatch(
    filename,
    content_type,
    data,
) -> None:
    with pytest.raises(UnsupportedAudioFormatError):
        validate_audio_bytes(data, filename=filename, content_type=content_type)


def test_read_audio_upload_rejects_non_audio_before_decoder() -> None:
    upload = UploadFile(
        file=BytesIO(b"# Changelog\nprivate build notes"),
        filename=r"C:\Users\private\CHANGELOG.md",
        headers=Headers({"content-type": "text/markdown"}),
    )

    with pytest.raises(UnsupportedAudioFormatError) as error:
        asyncio.run(read_audio_upload(upload, max_bytes=1024, field_name="audio"))

    assert "C:\\Users" not in str(error.value)
