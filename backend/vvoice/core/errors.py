class VVoiceError(Exception):
    pass


class ModelConfigurationError(VVoiceError):
    pass


class AudioError(VVoiceError):
    pass


class VoiceNotFoundError(VVoiceError):
    pass


class TtsJobNotFoundError(VVoiceError):
    pass


class AsrJobNotFoundError(VVoiceError):
    pass
