from vvoice.domains.tts.service import _normalize_zipvoice_text


def test_zipvoice_text_normalization_lowercases_vietnamese() -> None:
    assert (
        _normalize_zipvoice_text("  Xin   CHÀO, ĐÂY là Tiếng Việt.  ")
        == "xin chào, đây là tiếng việt."
    )
