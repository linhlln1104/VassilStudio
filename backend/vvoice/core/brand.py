from __future__ import annotations

import re


BRAND_NAME = "VassilStudio"
SPOKEN_BRAND_NAME = "Vassil Studio"
API_BRAND_NAME = f"{BRAND_NAME} API"


def prepare_spoken_brand_text(text: str) -> str:
    return re.sub(r"\bVassilStudio\b", SPOKEN_BRAND_NAME, text, flags=re.IGNORECASE)
