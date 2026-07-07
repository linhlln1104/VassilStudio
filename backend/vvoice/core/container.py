from __future__ import annotations

from dataclasses import dataclass

from vvoice.core.config import Settings
from vvoice.domains.asr.jobs import AsrJobService
from vvoice.domains.asr.service import AsrService
from vvoice.domains.tts.jobs import TtsJobService
from vvoice.domains.tts.service import ZipVoiceService
from vvoice.domains.voices.service import VoiceStore


@dataclass
class AppContainer:
    settings: Settings

    def __post_init__(self) -> None:
        self._ensure_storage_dirs()
        self.asr = AsrService(self.settings.asr, self.settings.runtime)
        self.tts = ZipVoiceService(self.settings.tts, self.settings.runtime)
        self.voices = VoiceStore(self.settings.storage.voices_dir)
        self.asr_jobs = AsrJobService(
            self.settings.storage.asr_jobs_dir,
            self.asr,
            target_sample_rate=self.settings.asr.sample_rate,
            max_workers=self.settings.jobs.asr_max_workers,
            max_attempts=self.settings.jobs.asr_max_attempts,
            retry_backoff_seconds=self.settings.jobs.retry_backoff_seconds,
        )
        self.tts_jobs = TtsJobService(
            self.settings.storage.tts_jobs_dir,
            self.tts,
            self.voices,
            max_workers=self.settings.jobs.tts_max_workers,
            max_attempts=self.settings.jobs.tts_max_attempts,
            retry_backoff_seconds=self.settings.jobs.retry_backoff_seconds,
            max_text_chars=self.settings.limits.max_tts_text_chars,
        )

    def shutdown(self) -> None:
        self.asr_jobs.shutdown()
        self.tts_jobs.shutdown()

    def _ensure_storage_dirs(self) -> None:
        for path in [
            self.settings.storage.data_dir,
            self.settings.storage.voices_dir,
            self.settings.storage.asr_jobs_dir,
            self.settings.storage.tts_jobs_dir,
            self.settings.storage.uploads_dir,
            self.settings.storage.outputs_dir,
            self.settings.storage.logs_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)
