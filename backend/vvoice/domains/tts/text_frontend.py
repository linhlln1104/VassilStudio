from __future__ import annotations

import re
import unicodedata
from functools import reduce
from pathlib import Path

from vvoice.core.config import TtsModelSettings
from vvoice.core.errors import ModelConfigurationError
from vvoice.shared.language import normalize_language


_LANGUAGE_TAG_PATTERN = re.compile(r"\(([a-z]{2,3}(?:-[a-z0-9]+)?)\)", re.IGNORECASE)


class ZipVoiceTextFrontend:
    def __init__(self) -> None:
        self._token_cache: dict[Path, set[str]] = {}
        self._token_id_cache: dict[Path, dict[str, int]] = {}

    def prepare(self, text: str, *, language: str, model_settings: TtsModelSettings) -> str:
        normalized_language = normalize_language(language)
        normalized_text = _normalize_input_text(text)

        phonemes = "".join(self._phonemize_espeak_tokens(normalized_text, normalized_language))
        self._validate_symbols(phonemes, model_settings.tokens)
        return phonemes

    def token_ids(self, text: str, *, language: str, model_settings: TtsModelSettings) -> list[int]:
        normalized_language = normalize_language(language)
        normalized_text = _normalize_input_text(text)
        tokens = self._phonemize_espeak_tokens(normalized_text, normalized_language)

        token_to_id = self._token_to_id(model_settings.tokens)
        missing = sorted({symbol for symbol in tokens if symbol not in token_to_id})
        if missing:
            rendered = ", ".join(repr(symbol) for symbol in missing[:12])
            raise ModelConfigurationError(
                f"ZipVoice {normalized_language} phonemizer produced symbols that are not in tokens.txt: {rendered}"
            )
        return [token_to_id[symbol] for symbol in tokens]

    def _phonemize_espeak_tokens(self, text: str, language: str) -> list[str]:
        try:
            from piper_phonemize import phonemize_espeak
        except Exception as exc:  # pragma: no cover - exercised by deployment smoke tests
            raise ModelConfigurationError(
                "ZipVoice requires piper_phonemize for its eSpeak tokenizer. "
                "Run `python -m pip install -e .` to refresh runtime dependencies."
            ) from exc

        espeak_language = "en-us" if language == "en" else language
        try:
            token_groups = phonemize_espeak(text, espeak_language)
            tokens = reduce(lambda left, right: left + right, token_groups) if token_groups else []
        except Exception as exc:
            raise ModelConfigurationError(f"ZipVoice {language} tokenization failed: {exc}") from exc

        return [token for token in tokens if not _LANGUAGE_TAG_PATTERN.fullmatch(token)]

    def _validate_symbols(self, phonemes: str, tokens_path: Path) -> None:
        tokens = self._tokens(tokens_path)
        missing = sorted({symbol for symbol in phonemes if symbol not in tokens})
        if missing:
            rendered = ", ".join(repr(symbol) for symbol in missing[:12])
            raise ModelConfigurationError(
                f"ZipVoice phonemizer produced symbols that are not in tokens.txt: {rendered}"
            )

    def _tokens(self, tokens_path: Path) -> set[str]:
        cached = self._token_cache.get(tokens_path)
        if cached is not None:
            return cached

        tokens: set[str] = set()
        for raw_line in tokens_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            token = " " if len(parts) == 1 else parts[0]
            tokens.add(token)

        self._token_cache[tokens_path] = tokens
        return tokens

    def _token_to_id(self, tokens_path: Path) -> dict[str, int]:
        cached = self._token_id_cache.get(tokens_path)
        if cached is not None:
            return cached

        token_to_id: dict[str, int] = {}
        for raw_line in tokens_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            if "\t" in raw_line:
                token, raw_id = raw_line.rstrip("\n").split("\t", 1)
            else:
                parts = raw_line.rsplit(" ", 1)
                if len(parts) != 2:
                    raise ModelConfigurationError(f"Malformed ZipVoice token line: {raw_line!r}")
                token, raw_id = parts
            token_to_id[token] = int(raw_id)

        self._token_id_cache[tokens_path] = token_to_id
        return token_to_id


def _normalize_input_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).strip().split())
