class VVoiceError(Exception):
    pass


PUBLIC_AUDIO_ERROR_MESSAGE = (
    "Audio could not be decoded. Use an uncorrupted WAV, MP3, WebM, FLAC, M4A, OGG, "
    "or Opus file."
)
PUBLIC_UNSUPPORTED_AUDIO_FORMAT_MESSAGE = (
    "Unsupported audio format. Use WAV, MP3, WebM, FLAC, M4A, OGG, or Opus."
)
PUBLIC_MODEL_ERROR_MESSAGE = (
    "The selected model is not ready. Check Settings > Diagnostics and the local logs."
)
PUBLIC_JOB_ERROR_MESSAGE = (
    "Processing failed. Check Settings > Diagnostics and the local logs."
)


class ModelConfigurationError(VVoiceError):
    pass


class AudioError(VVoiceError):
    pass


class UnsupportedAudioFormatError(AudioError):
    pass


class VoiceNotFoundError(VVoiceError):
    pass


class TtsJobNotFoundError(VVoiceError):
    pass


class AsrJobNotFoundError(VVoiceError):
    pass


class IdempotencyConflictError(VVoiceError):
    pass


class TranscriptRevisionConflictError(VVoiceError):
    pass


class TranscriptNotReadyError(VVoiceError):
    pass


def public_error_message(exc: Exception) -> str:
    if isinstance(exc, UnsupportedAudioFormatError):
        return PUBLIC_UNSUPPORTED_AUDIO_FORMAT_MESSAGE
    if isinstance(exc, AudioError):
        return PUBLIC_AUDIO_ERROR_MESSAGE
    if isinstance(exc, ModelConfigurationError):
        return PUBLIC_MODEL_ERROR_MESSAGE
    if isinstance(exc, VVoiceError):
        return str(exc)
    return PUBLIC_JOB_ERROR_MESSAGE


def public_job_error(message: str | None, failed_reason: str | None) -> str | None:
    if not message:
        return None
    if failed_reason == "cancelled":
        return "Job was cancelled"
    if failed_reason == "interrupted":
        return "Job was interrupted by server restart"
    if message in {
        PUBLIC_AUDIO_ERROR_MESSAGE,
        PUBLIC_JOB_ERROR_MESSAGE,
        PUBLIC_MODEL_ERROR_MESSAGE,
        PUBLIC_UNSUPPORTED_AUDIO_FORMAT_MESSAGE,
    }:
        return message
    return PUBLIC_JOB_ERROR_MESSAGE
