from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable


_CONTROL_TOKEN = re.compile(r"^<[^>]+>$")
_TERMINAL_PUNCTUATION = (".", "!", "?", "。", "！", "？")
_PAUSE_BOUNDARY_SECONDS = 0.8
_MAX_SEGMENT_SECONDS = 8.0


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str


def timed_segments_from_result(
    result: object,
    *,
    text: str,
    audio_duration_seconds: float,
) -> tuple[TranscriptSegment, ...]:
    native_segments = _native_segments(result, audio_duration_seconds)
    if native_segments:
        return native_segments

    return _token_segments(
        result,
        text=text,
        audio_duration_seconds=audio_duration_seconds,
    )


def segment_to_dict(segment: TranscriptSegment) -> dict[str, str | float]:
    return {
        "segment_id": segment.segment_id,
        "start_seconds": segment.start_seconds,
        "end_seconds": segment.end_seconds,
        "text": segment.text,
    }


def segments_from_metadata(value: object) -> tuple[TranscriptSegment, ...]:
    if not isinstance(value, (list, tuple)):
        return ()

    segments: list[TranscriptSegment] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, TranscriptSegment):
            segments.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        start = _finite_float(item.get("start_seconds"))
        end = _finite_float(item.get("end_seconds"))
        if not text or start is None or end is None or start < 0 or end <= start:
            continue
        segment_id = str(item.get("segment_id") or _segment_id(index)).strip()
        if not segment_id:
            segment_id = _segment_id(index)
        segments.append(
            TranscriptSegment(
                segment_id=segment_id,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                text=text,
            )
        )
    return tuple(segments)


def _native_segments(
    result: object,
    audio_duration_seconds: float,
) -> tuple[TranscriptSegment, ...]:
    texts = _sequence(_result_value(result, "segment_texts"))
    starts = _float_sequence(_result_value(result, "segment_timestamps"))
    durations = _float_sequence(_result_value(result, "segment_durations"))
    if not texts or len(texts) != len(starts) or len(texts) != len(durations):
        return ()

    segments: list[TranscriptSegment] = []
    for text_value, start, duration in zip(texts, starts, durations, strict=True):
        segment_text = str(text_value).strip()
        if not segment_text or start < 0 or duration <= 0:
            return ()
        end = start + duration
        if audio_duration_seconds > 0:
            end = min(end, audio_duration_seconds)
        if end <= start:
            return ()
        segments.append(
            TranscriptSegment(
                segment_id=_segment_id(len(segments) + 1),
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                text=segment_text,
            )
        )
    return tuple(segments)


def _token_segments(
    result: object,
    *,
    text: str,
    audio_duration_seconds: float,
) -> tuple[TranscriptSegment, ...]:
    tokens = _sequence(_result_value(result, "tokens"))
    timestamps = _float_sequence(_result_value(result, "timestamps"))
    if not text.strip() or not tokens or len(tokens) != len(timestamps):
        return ()

    timed_tokens: list[tuple[str, float]] = []
    for token_value, timestamp in zip(tokens, timestamps, strict=True):
        token = str(token_value)
        if not token or _CONTROL_TOKEN.match(token) or timestamp < 0:
            continue
        if audio_duration_seconds > 0 and timestamp >= audio_duration_seconds:
            return ()
        if timed_tokens and timestamp < timed_tokens[-1][1]:
            return ()
        timed_tokens.append((token, timestamp))

    if not timed_tokens:
        return ()

    groups: list[list[tuple[str, float]]] = []
    current: list[tuple[str, float]] = []
    for token, timestamp in timed_tokens:
        if current:
            pause = timestamp - current[-1][1]
            elapsed = timestamp - current[0][1]
            if pause >= _PAUSE_BOUNDARY_SECONDS or elapsed >= _MAX_SEGMENT_SECONDS:
                groups.append(current)
                current = []
        current.append((token, timestamp))
        if _render_tokens([token]).endswith(_TERMINAL_PUNCTUATION):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    rendered_groups = [_render_tokens(token for token, _ in group) for group in groups]
    if any(not rendered for rendered in rendered_groups):
        return ()

    # Some tokenizers expose control or byte pieces that cannot be rendered faithfully.
    # In that case, preserve the model text as one timed segment instead of changing words.
    if _comparable_text(" ".join(rendered_groups)) != _comparable_text(text):
        rendered_groups = [text.strip()]
        groups = [timed_tokens]

    segments: list[TranscriptSegment] = []
    for index, (group, segment_text) in enumerate(zip(groups, rendered_groups, strict=True)):
        start = group[0][1]
        if index + 1 < len(groups):
            end = groups[index + 1][0][1]
        else:
            end = audio_duration_seconds
        if end <= start:
            end = (
                min(audio_duration_seconds, start + 0.001)
                if audio_duration_seconds > start
                else start + 0.001
            )
        segments.append(
            TranscriptSegment(
                segment_id=_segment_id(index + 1),
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                text=segment_text,
            )
        )
    return tuple(segments)


def _render_tokens(tokens: Iterable[str]) -> str:
    rendered = "".join(tokens).replace("▁", " ").replace("Ġ", " ")
    rendered = re.sub(r"\s+", " ", rendered).strip()
    rendered = re.sub(r"\s+([,.;:!?%])", r"\1", rendered)
    return rendered


def _comparable_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _sequence(value: object) -> list[object]:
    if value is None or isinstance(value, (str, bytes)):
        return []
    try:
        return list(value)  # type: ignore[arg-type]
    except TypeError:
        return []


def _result_value(result: object, field: str) -> object:
    try:
        return getattr(result, field, ())
    except Exception:
        return ()


def _float_sequence(value: object) -> list[float]:
    result: list[float] = []
    for item in _sequence(value):
        number = _finite_float(item)
        if number is None:
            return []
        result.append(number)
    return result


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _segment_id(index: int) -> str:
    return f"segment-{index:04d}"
