import asyncio
from io import BytesIO

import pytest
from fastapi import UploadFile

from vvoice.core.errors import VVoiceError
from vvoice.shared.validation import read_upload_file, safe_display_filename, validate_text_field


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
