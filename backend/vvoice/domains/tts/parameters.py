from __future__ import annotations

import math

from vvoice.core.errors import VVoiceError


MIN_NUM_STEPS = 1
MAX_NUM_STEPS = 64
MIN_SPEED = 0.5
MAX_SPEED = 2.0


def validate_tts_parameters(num_steps: int | None, speed: float | None) -> None:
    if num_steps is not None and not MIN_NUM_STEPS <= num_steps <= MAX_NUM_STEPS:
        raise VVoiceError(f"num_steps must be between {MIN_NUM_STEPS} and {MAX_NUM_STEPS}.")

    if speed is not None:
        if not math.isfinite(speed) or not MIN_SPEED <= speed <= MAX_SPEED:
            raise VVoiceError(f"speed must be between {MIN_SPEED:.1f} and {MAX_SPEED:.1f}.")
