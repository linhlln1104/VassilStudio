from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vvoice.core.config import RuntimeSettings, TtsModelSettings
from vvoice.core.errors import ModelConfigurationError
from vvoice.domains.tts.text_frontend import ZipVoiceTextFrontend


@dataclass(frozen=True)
class ZipVoiceOnnxOutput:
    samples: np.ndarray
    sample_rate: int


class ZipVoiceOnnxRuntime:
    def __init__(
        self,
        *,
        model_settings: TtsModelSettings,
        runtime_settings: RuntimeSettings,
        text_frontend: ZipVoiceTextFrontend,
    ) -> None:
        self._model = model_settings
        self._runtime = runtime_settings
        self._text_frontend = text_frontend
        self._target_rms = 0.1
        self._feat_scale = 0.1
        self._t_shift = 0.5
        self._guidance_scale = 1.0
        self._n_fft = 1024
        self._hop_length = 256
        self._win_length = 1024
        self._num_mels = 100
        self._text_encoder = None
        self._flow_decoder = None
        self._vocoder = None
        self._mel_transform = None
        self._vocoder_meta: dict[str, str] = {}

    def load(self) -> None:
        self._validate_runtime_dependencies()

        import onnxruntime as ort
        import torchaudio

        session_options = ort.SessionOptions()
        session_options.inter_op_num_threads = self._runtime.effective_tts_num_threads
        session_options.intra_op_num_threads = self._runtime.effective_tts_num_threads

        providers = ["CPUExecutionProvider"]
        self._text_encoder = ort.InferenceSession(
            str(self._model.encoder),
            sess_options=session_options,
            providers=providers,
        )
        self._flow_decoder = ort.InferenceSession(
            str(self._model.decoder),
            sess_options=session_options,
            providers=providers,
        )
        self._vocoder = ort.InferenceSession(
            str(self._model.vocoder),
            sess_options=session_options,
            providers=providers,
        )
        self._vocoder_meta = self._vocoder.get_modelmeta().custom_metadata_map
        self._mel_transform = torchaudio.transforms.MelSpectrogram(
            sample_rate=self._model.sample_rate,
            n_fft=self._n_fft,
            hop_length=self._hop_length,
            n_mels=self._num_mels,
            center=True,
            power=1,
        )

    def synthesize(
        self,
        *,
        text: str,
        reference_audio: np.ndarray,
        reference_sample_rate: int,
        reference_text: str,
        num_steps: int,
        speed: float,
    ) -> ZipVoiceOnnxOutput:
        self._ensure_loaded()
        if num_steps <= 0:
            raise ModelConfigurationError("ZipVoice num_steps must be greater than 0.")
        if speed <= 0:
            raise ModelConfigurationError("ZipVoice speed must be greater than 0.")

        prompt_tokens = self._text_frontend.token_ids(
            _add_punctuation(reference_text),
            language=self._model.language,
            model_settings=self._model,
        )
        tokens = self._text_frontend.token_ids(
            _add_punctuation(text),
            language=self._model.language,
            model_settings=self._model,
        )
        if not tokens or not prompt_tokens:
            raise ModelConfigurationError("ZipVoice tokenizer returned empty tokens.")

        import torch

        torch.manual_seed(666)
        prompt_wav = self._prepare_prompt(reference_audio, reference_sample_rate)
        prompt_rms = torch.sqrt(torch.mean(torch.square(prompt_wav)))
        if 0 < prompt_rms < self._target_rms:
            prompt_wav = prompt_wav * self._target_rms / prompt_rms

        prompt_features = self._extract_prompt_features(prompt_wav) * self._feat_scale
        pred_features = self._sample(
            tokens=tokens,
            prompt_tokens=prompt_tokens,
            prompt_features=prompt_features,
            speed=speed,
            num_steps=num_steps,
        )
        mel = pred_features.permute(0, 2, 1) / self._feat_scale
        waveform = self._decode_vocos(mel)
        waveform = waveform.clamp(-1, 1)
        if 0 < prompt_rms < self._target_rms:
            waveform = waveform * prompt_rms / self._target_rms

        return ZipVoiceOnnxOutput(
            samples=waveform.cpu().numpy().astype(np.float32),
            sample_rate=self._model.sample_rate,
        )

    def _ensure_loaded(self) -> None:
        if self._text_encoder is None:
            self.load()

    def _prepare_prompt(self, audio: np.ndarray, sample_rate: int):
        import librosa
        import torch

        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        if sample_rate != self._model.sample_rate:
            samples = librosa.resample(
                samples,
                orig_sr=sample_rate,
                target_sr=self._model.sample_rate,
            ).astype(np.float32)
        return torch.from_numpy(samples).unsqueeze(0)

    def _extract_prompt_features(self, prompt_wav):
        import torch

        assert self._mel_transform is not None
        mel = self._mel_transform(prompt_wav)
        logmel = mel.clamp(min=1e-7).log()
        logmel = logmel.reshape(-1, logmel.shape[-1]).transpose(0, 1)

        num_frames = _compute_num_frames(
            num_samples=prompt_wav.shape[1],
            hop_length=self._hop_length,
        )
        if logmel.shape[0] > num_frames:
            logmel = logmel[:num_frames]
        elif logmel.shape[0] < num_frames:
            logmel = torch.nn.functional.pad(
                logmel.unsqueeze(0),
                (0, 0, 0, num_frames - logmel.shape[0]),
                mode="replicate",
            ).squeeze(0)

        return logmel.unsqueeze(0)

    def _sample(
        self,
        *,
        tokens: list[int],
        prompt_tokens: list[int],
        prompt_features,
        speed: float,
        num_steps: int,
    ):
        import torch

        assert self._text_encoder is not None
        assert self._flow_decoder is not None

        tokens_tensor = np.asarray([tokens], dtype=np.int64)
        prompt_tokens_tensor = np.asarray([prompt_tokens], dtype=np.int64)
        prompt_features_len = np.asarray(prompt_features.shape[1], dtype=np.int64)
        speed_tensor = np.asarray(float(speed), dtype=np.float32)

        text_inputs = self._text_encoder.get_inputs()
        text_condition_np = self._text_encoder.run(
            [self._text_encoder.get_outputs()[0].name],
            {
                text_inputs[0].name: tokens_tensor,
                text_inputs[1].name: prompt_tokens_tensor,
                text_inputs[2].name: prompt_features_len,
                text_inputs[3].name: speed_tensor,
            },
        )[0]
        text_condition = torch.from_numpy(text_condition_np)
        batch_size, num_frames, feat_dim = text_condition.shape
        x = torch.randn(batch_size, num_frames, feat_dim)
        speech_condition = torch.nn.functional.pad(
            prompt_features,
            (0, 0, 0, num_frames - prompt_features.shape[1]),
        )
        guidance_scale = np.asarray(self._guidance_scale, dtype=np.float32)
        timesteps = _time_steps(num_steps, self._t_shift)

        decoder_inputs = self._flow_decoder.get_inputs()
        decoder_output = self._flow_decoder.get_outputs()[0].name
        for step in range(num_steps):
            velocity_np = self._flow_decoder.run(
                [decoder_output],
                {
                    decoder_inputs[0].name: np.asarray(timesteps[step].item(), dtype=np.float32),
                    decoder_inputs[1].name: x.numpy(),
                    decoder_inputs[2].name: text_condition.numpy(),
                    decoder_inputs[3].name: speech_condition.numpy(),
                    decoder_inputs[4].name: guidance_scale,
                },
            )[0]
            velocity = torch.from_numpy(velocity_np)
            x = x + velocity * (timesteps[step + 1] - timesteps[step])

        return x[:, prompt_features.shape[1] :, :]

    def _decode_vocos(self, mel):
        import torch

        assert self._vocoder is not None
        vocoder_inputs = self._vocoder.get_inputs()
        outputs = self._vocoder.run(
            [output.name for output in self._vocoder.get_outputs()],
            {vocoder_inputs[0].name: mel.numpy().astype(np.float32)},
        )
        mag, x, y = [torch.from_numpy(output) for output in outputs]
        stft = torch.complex((mag * x)[0], (mag * y)[0])

        n_fft = int(self._vocoder_meta.get("n_fft", self._n_fft))
        hop_length = int(self._vocoder_meta.get("hop_length", self._hop_length))
        win_length = int(self._vocoder_meta.get("win_length", self._win_length))
        center = bool(int(self._vocoder_meta.get("center", "1")))
        normalized = bool(int(self._vocoder_meta.get("normalized", "0")))
        window_type = self._vocoder_meta.get("window_type", "hann")
        if window_type != "hann":
            raise ModelConfigurationError(f"Unsupported Vocos window type: {window_type}")

        window = torch.hann_window(win_length)
        return torch.istft(
            stft,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=win_length,
            window=window,
            center=center,
            normalized=normalized,
        )

    def _validate_runtime_dependencies(self) -> None:
        try:
            import onnxruntime  # noqa: F401
            import torch  # noqa: F401
            import torchaudio  # noqa: F401
        except Exception as exc:  # pragma: no cover - exercised by deployment smoke tests
            raise ModelConfigurationError(
                "Vietnamese ZipVoice ONNX requires onnxruntime, torch, and torchaudio. "
                "Run `python -m pip install -e \".[runtime]\"` to install model runtime dependencies."
            ) from exc


def _add_punctuation(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    return text if text[-1] in {";", ":", ",", ".", "!", "?"} else f"{text}."


def _compute_num_frames(*, num_samples: int, hop_length: int) -> int:
    return int((num_samples + hop_length // 2) // hop_length)


def _time_steps(num_steps: int, t_shift: float):
    import torch

    timesteps = torch.linspace(0.0, 1.0, num_steps + 1)
    return t_shift * timesteps / (1 + (t_shift - 1) * timesteps)
