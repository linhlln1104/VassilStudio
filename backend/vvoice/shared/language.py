from __future__ import annotations

from vvoice.core.errors import VVoiceError


DEFAULT_LANGUAGE = "vi"
SUPPORTED_LANGUAGES = {
    "vi": "Vietnamese",
    "en": "English",
}
LANGUAGE_ALIASES = {
    "vietnamese": "vi",
    "vie": "vi",
    "vi-vn": "vi",
    "english": "en",
    "eng": "en",
    "en-us": "en",
}


def normalize_language(value: str | None) -> str:
    normalized = (value or DEFAULT_LANGUAGE).strip().lower()
    normalized = LANGUAGE_ALIASES.get(normalized, normalized)
    if normalized not in SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise VVoiceError(f"Unsupported language '{value}'. Supported languages: {supported}")
    return normalized
