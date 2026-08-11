from pathlib import Path

from vvoice.core.config import TtsModelSettings
from vvoice.domains.tts.text_frontend import ZipVoiceTextFrontend


VI_TEXT = "xin ch\u00e0o, \u0111\u00e2y l\u00e0 v voice"
VI_PHONEMES = "s\u02c8in t\u0283\u02c8a\u02d02w, \u0257\u02c8\u0259\u026a l\u02cca\u02d02 v\u02c8e v\u02c8\u0254\u026as"
EN_TEXT = "Hello, this is a clear English voice test."
EN_PHONEMES = "h\u0259l\u02c8o\u028a, \u00f0\u026as \u026az \u0250 kl\u02c8\u026a\u0279 \u02c8\u026a\u014b\u0261l\u026a\u0283 v\u02c8\u0254\u026as t\u02c8\u025bst."


def _model_settings(tmp_path: Path, *, language: str, phonemes: str) -> TtsModelSettings:
    tokens = tmp_path / f"{language}-tokens.txt"
    symbols = tuple(dict.fromkeys(phonemes))
    tokens.write_text(
        "".join(f"{symbol}\t{index}\n" for index, symbol in enumerate(symbols)),
        encoding="utf-8",
    )
    return TtsModelSettings(
        language=language,
        label=language.upper(),
        sample_rate=24_000,
        default_num_steps=4,
        default_speed=1.0,
        min_char_in_sentence=2,
        tokens=tokens,
        encoder=tmp_path / "encoder.onnx",
        decoder=tmp_path / "decoder.onnx",
        vocoder=tmp_path / "vocoder.onnx",
        data_dir=tmp_path,
        lexicon=tokens,
    )


def _expected_ids(phonemes: str) -> list[int]:
    symbol_ids = {symbol: index for index, symbol in enumerate(dict.fromkeys(phonemes))}
    return [symbol_ids[symbol] for symbol in phonemes]


def test_vietnamese_zipvoice_frontend_phonemizes_text(tmp_path: Path) -> None:
    frontend = ZipVoiceTextFrontend()
    model = _model_settings(tmp_path, language="vi", phonemes=VI_PHONEMES)

    phonemes = frontend.prepare(
        VI_TEXT,
        language="vi",
        model_settings=model,
    )

    assert phonemes == VI_PHONEMES
    assert "xin" not in phonemes
    assert "ch\u00e0o" not in phonemes
    assert "\u02c8" in phonemes
    assert "t\u0283" in phonemes
    assert "(en)" not in phonemes
    assert "(vi)" not in phonemes


def test_zipvoice_frontend_has_stable_espeak_output(tmp_path: Path) -> None:
    frontend = ZipVoiceTextFrontend()
    vi_phonemes = "s\u02c8in t\u0283\u02c8a\u02d02w"
    en_phonemes = "h\u0259l\u02c8o\u028a w\u02c8\u025c\u02d0ld"

    assert frontend.prepare(
        "xin ch\u00e0o",
        language="vi",
        model_settings=_model_settings(tmp_path, language="vi", phonemes=vi_phonemes),
    ) == vi_phonemes
    assert frontend.prepare(
        "hello world",
        language="en",
        model_settings=_model_settings(tmp_path, language="en", phonemes=en_phonemes),
    ) == en_phonemes


def test_vietnamese_zipvoice_frontend_returns_model_token_ids(tmp_path: Path) -> None:
    frontend = ZipVoiceTextFrontend()
    model = _model_settings(tmp_path, language="vi", phonemes=VI_PHONEMES)

    token_ids = frontend.token_ids(
        VI_TEXT,
        language="vi",
        model_settings=model,
    )

    assert token_ids == _expected_ids(VI_PHONEMES)


def test_english_zipvoice_frontend_returns_model_token_ids(tmp_path: Path) -> None:
    frontend = ZipVoiceTextFrontend()
    model = _model_settings(tmp_path, language="en", phonemes=EN_PHONEMES)

    token_ids = frontend.token_ids(
        EN_TEXT,
        language="en",
        model_settings=model,
    )

    assert token_ids == _expected_ids(EN_PHONEMES)
