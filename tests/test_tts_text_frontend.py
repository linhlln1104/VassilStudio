from vvoice.core.config import load_settings
from vvoice.domains.tts.text_frontend import ZipVoiceTextFrontend


def test_vietnamese_zipvoice_frontend_phonemizes_text() -> None:
    settings = load_settings()
    frontend = ZipVoiceTextFrontend()
    model = settings.tts.model_for("vi")

    phonemes = frontend.prepare(
        "xin ch\u00e0o, \u0111\u00e2y l\u00e0 v voice",
        language="vi",
        model_settings=model,
    )

    assert "xin" not in phonemes
    assert "ch\u00e0o" not in phonemes
    assert "\u02c8" in phonemes
    assert "t\u0283" in phonemes
    assert "(en)" not in phonemes
    assert "(vi)" not in phonemes


def test_zipvoice_frontend_has_stable_espeak_output() -> None:
    settings = load_settings()
    frontend = ZipVoiceTextFrontend()

    assert frontend.prepare(
        "xin ch\u00e0o",
        language="vi",
        model_settings=settings.tts.model_for("vi"),
    ) == "s\u02c8in t\u0283\u02c8a\u02d02w"
    assert frontend.prepare(
        "hello world",
        language="en",
        model_settings=settings.tts.model_for("en"),
    ) == "h\u0259l\u02c8o\u028a w\u02c8\u025c\u02d0ld"


def test_vietnamese_zipvoice_frontend_returns_model_token_ids() -> None:
    settings = load_settings()
    frontend = ZipVoiceTextFrontend()
    model = settings.tts.model_for("vi")

    token_ids = frontend.token_ids(
        "xin ch\u00e0o, \u0111\u00e2y l\u00e0 v voice",
        language="vi",
        model_settings=model,
    )

    assert token_ids
    assert all(isinstance(token_id, int) for token_id in token_ids)
    assert max(token_ids) < 360


def test_english_zipvoice_frontend_returns_model_token_ids() -> None:
    settings = load_settings()
    frontend = ZipVoiceTextFrontend()
    model = settings.tts.model_for("en")

    token_ids = frontend.token_ids(
        "Hello, this is a clear English voice test.",
        language="en",
        model_settings=model,
    )

    assert token_ids
    assert all(isinstance(token_id, int) for token_id in token_ids)
    assert max(token_ids) < 763
