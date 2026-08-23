from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Literal
import unicodedata

import librosa
import numpy as np

from vvoice.core.errors import VVoiceError
from vvoice.shared.audio.io import encode_wav, load_audio_bytes_with_metadata


MIN_REFERENCE_SECONDS = 1.0
RECOMMENDED_MIN_SECONDS = 3.0
RECOMMENDED_MAX_SECONDS = 20.0
MAX_REFERENCE_SECONDS = 60.0
SILENCE_RMS = 0.01
SILENCE_WARNING_SECONDS = 0.5
LOW_SPEECH_COVERAGE_RATIO = 0.55
NO_SPEECH_COVERAGE_RATIO = 0.05
CLIPPING_SAMPLE_LEVEL = 0.999
CLIPPING_WARNING_RATIO = 0.001
SEVERE_CLIPPING_RATIO = 0.1
TRIM_PADDING_SECONDS = 0.1


@dataclass(frozen=True)
class VoiceIntakeIssue:
    code: str
    severity: Literal["warning", "blocking"]
    message: str


@dataclass(frozen=True)
class SignalMetrics:
    leading_silence_seconds: float
    trailing_silence_seconds: float
    speech_coverage_ratio: float
    clipping_ratio: float
    peak_amplitude: float
    active_start_seconds: float | None
    active_end_seconds: float | None


@dataclass(frozen=True)
class PreparedVoiceAudio:
    source_sha256: str
    audio_sha256: str
    audio_bytes: bytes
    samples: np.ndarray
    source_sample_rate: int
    target_sample_rate: int
    channels: int
    source_duration_seconds: float
    duration_seconds: float
    trim_start_seconds: float
    trim_end_seconds: float
    suggested_trim_start_seconds: float
    suggested_trim_end_seconds: float
    metrics: SignalMetrics
    issues: tuple[VoiceIntakeIssue, ...]


def prepare_voice_audio(
    raw_audio: bytes,
    *,
    target_sample_rate: int,
    trim_start_seconds: float = 0.0,
    trim_end_seconds: float | None = None,
) -> PreparedVoiceAudio:
    source_samples, source_sample_rate, channels = load_audio_bytes_with_metadata(raw_audio)
    source_duration = len(source_samples) / source_sample_rate
    trim_start, trim_end = _validate_trim_bounds(
        trim_start_seconds,
        trim_end_seconds,
        source_duration,
    )

    full_metrics = _signal_metrics(source_samples, source_sample_rate)
    start_index = min(len(source_samples), round(trim_start * source_sample_rate))
    end_index = min(len(source_samples), round(trim_end * source_sample_rate))
    selected_source_samples = source_samples[start_index:end_index]
    if selected_source_samples.size == 0:
        raise VVoiceError("The selected trim range contains no audio samples")

    metrics = _signal_metrics(selected_source_samples, source_sample_rate)
    if source_sample_rate == target_sample_rate:
        selected_samples = np.asarray(selected_source_samples, dtype=np.float32)
    else:
        selected_samples = np.asarray(
            librosa.resample(
                selected_source_samples,
                orig_sr=source_sample_rate,
                target_sr=target_sample_rate,
            ),
            dtype=np.float32,
        )

    audio_bytes = encode_wav(selected_samples, target_sample_rate)
    duration = len(selected_source_samples) / source_sample_rate
    suggested_start, suggested_end = _suggested_trim(full_metrics, source_duration)
    issues = tuple(_audio_quality_issues(duration, metrics))
    return PreparedVoiceAudio(
        source_sha256=hashlib.sha256(raw_audio).hexdigest(),
        audio_sha256=hashlib.sha256(audio_bytes).hexdigest(),
        audio_bytes=audio_bytes,
        samples=selected_samples,
        source_sample_rate=source_sample_rate,
        target_sample_rate=target_sample_rate,
        channels=channels,
        source_duration_seconds=source_duration,
        duration_seconds=duration,
        trim_start_seconds=trim_start,
        trim_end_seconds=trim_end,
        suggested_trim_start_seconds=suggested_start,
        suggested_trim_end_seconds=suggested_end,
        metrics=metrics,
        issues=issues,
    )


def reference_text_issues(reference_text: str | None, language: str) -> tuple[VoiceIntakeIssue, ...]:
    text = (reference_text or "").strip()
    if not text:
        return (
            VoiceIntakeIssue(
                code="reference_text_missing",
                severity="blocking",
                message="Add or generate an exact transcript before creating this voice profile.",
            ),
        )

    if not any(character.isalpha() for character in text):
        return (
            VoiceIntakeIssue(
                code="reference_text_has_no_words",
                severity="blocking",
                message="Reference text must contain spoken words, not only numbers or punctuation.",
            ),
        )

    if language == "en":
        if any(character.casefold() in "ăđơư" for character in text):
            return (
                VoiceIntakeIssue(
                    code="reference_text_language_mismatch",
                    severity="blocking",
                    message="The transcript contains Vietnamese-specific letters but the profile language is English.",
                ),
            )
        if _vietnamese_tone_mark_count(text) >= 2:
            return (
                VoiceIntakeIssue(
                    code="reference_text_language_mismatch",
                    severity="blocking",
                    message="The transcript contains several Vietnamese tone marks but the profile language is English.",
                ),
            )

    if language == "vi" and _vietnamese_marker_count(text) == 0:
        return (
            VoiceIntakeIssue(
                code="reference_text_diacritics_review",
                severity="warning",
                message="The Vietnamese transcript has no diacritics. Verify that it exactly matches the recording.",
            ),
        )
    return ()


def intake_status(
    issues: tuple[VoiceIntakeIssue, ...] | list[VoiceIntakeIssue],
) -> Literal["ready", "review", "blocked"]:
    if any(issue.severity == "blocking" for issue in issues):
        return "blocked"
    if issues:
        return "review"
    return "ready"


def _validate_trim_bounds(
    start_seconds: float,
    end_seconds: float | None,
    duration_seconds: float,
) -> tuple[float, float]:
    start = float(start_seconds)
    end = duration_seconds if end_seconds is None else float(end_seconds)
    if not math.isfinite(start) or not math.isfinite(end):
        raise VVoiceError("Trim boundaries must be finite numbers")
    if start < 0:
        raise VVoiceError("trim_start_seconds must be zero or greater")
    if end <= start:
        raise VVoiceError("trim_end_seconds must be greater than trim_start_seconds")
    tolerance = 0.001
    if end > duration_seconds + tolerance:
        raise VVoiceError("trim_end_seconds exceeds the source audio duration")
    if start >= duration_seconds:
        raise VVoiceError("trim_start_seconds must be before the end of the source audio")
    return min(start, duration_seconds), min(end, duration_seconds)


def _signal_metrics(samples: np.ndarray, sample_rate: int) -> SignalMetrics:
    absolute = np.abs(samples)
    peak = float(np.max(absolute)) if samples.size else 0.0
    clipping_ratio = float(np.mean(absolute >= CLIPPING_SAMPLE_LEVEL)) if samples.size else 0.0
    duration = len(samples) / sample_rate
    frame_samples = max(1, round(sample_rate * 0.02))
    hop_samples = max(1, round(sample_rate * 0.01))
    starts = list(range(0, max(1, len(samples) - frame_samples + 1), hop_samples))
    if not starts or starts[-1] + frame_samples < len(samples):
        starts.append(max(0, len(samples) - frame_samples))

    rms_values = []
    for start in starts:
        frame = samples[start : start + frame_samples]
        rms_values.append(float(np.sqrt(np.mean(np.square(frame), dtype=np.float64))))
    active_indices = [index for index, rms in enumerate(rms_values) if rms >= SILENCE_RMS]
    if not active_indices:
        return SignalMetrics(
            leading_silence_seconds=duration,
            trailing_silence_seconds=duration,
            speech_coverage_ratio=0.0,
            clipping_ratio=clipping_ratio,
            peak_amplitude=peak,
            active_start_seconds=None,
            active_end_seconds=None,
        )

    first_start = starts[active_indices[0]] / sample_rate
    last_end = min(duration, (starts[active_indices[-1]] + frame_samples) / sample_rate)
    return SignalMetrics(
        leading_silence_seconds=first_start,
        trailing_silence_seconds=max(0.0, duration - last_end),
        speech_coverage_ratio=len(active_indices) / len(rms_values),
        clipping_ratio=clipping_ratio,
        peak_amplitude=peak,
        active_start_seconds=first_start,
        active_end_seconds=last_end,
    )


def _suggested_trim(metrics: SignalMetrics, duration_seconds: float) -> tuple[float, float]:
    if metrics.active_start_seconds is None or metrics.active_end_seconds is None:
        return 0.0, duration_seconds
    return (
        max(0.0, metrics.active_start_seconds - TRIM_PADDING_SECONDS),
        min(duration_seconds, metrics.active_end_seconds + TRIM_PADDING_SECONDS),
    )


def _audio_quality_issues(
    duration_seconds: float,
    metrics: SignalMetrics,
) -> list[VoiceIntakeIssue]:
    issues: list[VoiceIntakeIssue] = []
    if duration_seconds < MIN_REFERENCE_SECONDS:
        issues.append(
            VoiceIntakeIssue(
                code="audio_too_short",
                severity="blocking",
                message="The selected reference must be at least 1 second long.",
            )
        )
    elif duration_seconds < RECOMMENDED_MIN_SECONDS:
        issues.append(
            VoiceIntakeIssue(
                code="audio_short",
                severity="warning",
                message="References under 3 seconds may not capture enough voice detail.",
            )
        )
    elif duration_seconds > MAX_REFERENCE_SECONDS:
        issues.append(
            VoiceIntakeIssue(
                code="audio_too_long",
                severity="blocking",
                message="Trim the reference to 60 seconds or less before saving it.",
            )
        )
    elif duration_seconds > RECOMMENDED_MAX_SECONDS:
        issues.append(
            VoiceIntakeIssue(
                code="audio_long",
                severity="warning",
                message="References over 20 seconds increase processing time. Keep only the cleanest passage.",
            )
        )

    if metrics.speech_coverage_ratio < NO_SPEECH_COVERAGE_RATIO:
        issues.append(
            VoiceIntakeIssue(
                code="speech_not_detected",
                severity="blocking",
                message="No usable speech signal was detected in the selected range.",
            )
        )
    elif metrics.speech_coverage_ratio < LOW_SPEECH_COVERAGE_RATIO:
        issues.append(
            VoiceIntakeIssue(
                code="speech_coverage_low",
                severity="warning",
                message="Speech covers less than 55% of the selection. Trim long pauses for a cleaner reference.",
            )
        )

    if metrics.leading_silence_seconds >= SILENCE_WARNING_SECONDS:
        issues.append(
            VoiceIntakeIssue(
                code="leading_silence",
                severity="warning",
                message="The selection begins with at least 0.5 seconds of silence.",
            )
        )
    if metrics.trailing_silence_seconds >= SILENCE_WARNING_SECONDS:
        issues.append(
            VoiceIntakeIssue(
                code="trailing_silence",
                severity="warning",
                message="The selection ends with at least 0.5 seconds of silence.",
            )
        )

    if metrics.clipping_ratio >= SEVERE_CLIPPING_RATIO:
        issues.append(
            VoiceIntakeIssue(
                code="severe_clipping",
                severity="blocking",
                message="Severe clipping affects at least 10% of the selected samples. Use another recording.",
            )
        )
    elif metrics.clipping_ratio >= CLIPPING_WARNING_RATIO:
        issues.append(
            VoiceIntakeIssue(
                code="clipping_detected",
                severity="warning",
                message="Clipped samples were detected. Listen for distortion before accepting this reference.",
            )
        )
    return issues


def _vietnamese_marker_count(text: str) -> int:
    return sum(
        1
        for character in text
        if character.casefold() in "ăâđêôơư" or _character_has_vietnamese_tone(character)
    )


def _vietnamese_tone_mark_count(text: str) -> int:
    return sum(1 for character in text if _character_has_vietnamese_tone(character))


def _character_has_vietnamese_tone(character: str) -> bool:
    decomposition = unicodedata.normalize("NFD", character)
    return any(mark in decomposition for mark in ("\u0300", "\u0301", "\u0303", "\u0309", "\u0323"))
