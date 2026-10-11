# Model engines and deployments

VassilStudio separates application workflows from TTS inference. The first two engine
implementations are ZipVoice ONNX and VieNeu TTS v3 Turbo. ZipFormer remains the ASR
implementation; a TTS engine is not an ASR provider.

## Boundaries

```text
Studio / HTTP API
  -> TtsJobService: admission, reference snapshot, idempotency, cancellation, persistence
  -> TtsService: resolve model_id, validate capabilities, serialize each model, lifecycle
  -> TtsRegistry: explicit engine -> adapter factory
       zipvoice -> tokenizer + ONNX/Torch runtime in the API environment
       vieneu   -> persistent offline worker in a separate Python environment
```

The common interface lives in `backend/vvoice/inference/tts/base.py`. ZipVoice-specific
phonemization and inference live under `inference/tts/zipvoice/`. VieNeu integration is
in `inference/tts/vieneu.py` and `vieneu_worker.py`. Domain routers and jobs do not
import either model SDK. The old ZipVoice module paths remain compatibility imports.

Three different identifiers have distinct purposes:

- **Engine** selects an implementation, such as `zipvoice` or `vieneu`.
- **Model ID** identifies a configured deployment/checkpoint, such as `zipvoice-vi`
  or `vieneu-v3-turbo`. Multiple IDs can use one engine and one language.
- **Language** selects a language supported by that deployment. It does not identify
  the model family. The current product supports Vietnamese and English.

Voice profiles keep source WAV audio and transcripts, rather than engine-specific
embeddings. The same reference can therefore be supplied to either adapter. ZipVoice
uses the transcript; VieNeu v3 Turbo conditions on reference audio and ignores that
legacy transcript field. This first integration uses reference voices, not VieNeu's
built-in presets or streaming API.

## Configuration

`config/vassil.example.json` contains two ZipVoice deployments and one bilingual VieNeu
deployment. Copy it to `config/vassil.local.json` and set `VASSIL_CONFIG` to that file
for local changes. Each profile supplies an engine, display label, languages, output
sample rate, and engine-owned options:

```json
{
  "tts": {
    "enabled": true,
    "default_language": "vi",
    "default_models": {"vi": "vieneu-v3-turbo", "en": "vieneu-v3-turbo"},
    "profiles": {
      "vieneu-v3-turbo": {
        "engine": "vieneu",
        "label": "VieNeu TTS v3 Turbo",
        "languages": ["vi", "en"],
        "sample_rate": 48000,
        "options": {
          "environment_dir": ".venv-vieneu",
          "model_dir": "models/runtime/tts/vieneu-v3-turbo/model",
          "onnx_dir": "models/runtime/tts/vieneu-v3-turbo/model/onnx_update",
          "cache_dir": "models/runtime/tts/vieneu-v3-turbo/hf-cache",
          "threads": 0,
          "denoise": true,
          "load_timeout_seconds": 180,
          "inference_timeout_seconds": 600
        }
      }
    }
  }
}
```

This is only the TTS section; retain the rest of the application configuration.
Relative asset/environment paths resolve against `VASSIL_ROOT`/the repository root.
`default_models` must cover every configured language and point to a matching profile.
IDs are stable and case-sensitive. Do not repurpose an existing ID for an unrelated
checkpoint: persisted jobs refer to the ID, not a full copy of its weights/configuration.
Changing files under an existing ID can change later reruns.

Legacy `tts.models.vi`/`tts.models.en` and single-model settings are still accepted
and converted to `zipvoice-vi`/`zipvoice-en`. Do not combine `profiles` and `models`.
Old saved jobs without `model_id` retain their original ZipVoice language selection.
New jobs and idempotency fingerprints record the resolved model ID, so changing the
default model does not redirect already accepted jobs or idempotent replays.

## Engine installation

The API/UI can run with `pip install -e ".[server]"`. Model engines are optional.
There is no automatic model download during app startup, catalog checks, or inference.

### ZipVoice and ZipFormer

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e ".[server,zipvoice,zipformer]"
```

`.[runtime]` and `.[dev]` retain their combined Zip installation behavior. Existing
Zip model directories remain valid. The repository does not distribute model weights.
To prepare the example TTS profiles explicitly:

```powershell
# English upstream ONNX + Vietnamese originating PyTorch checkpoint + Vocos:
.\.venv\Scripts\python.exe scripts/setup_zipvoice.py --download-assets

# Vietnamese requires a local ONNX export. The exporter checks this exact clean checkout:
git clone https://github.com/k2-fsa/ZipVoice.git foundation/ZipVoice
git -C foundation/ZipVoice checkout 2f7326fbfe999a3ad179e3f1af82a424d4a62819
.\.venv\Scripts\python.exe -m pip install onnx==1.23.2 tensorboard==2.21.0
.\.venv\Scripts\python.exe scripts/export_zipvoice_vi.py
```

If the upstream checkout already exists, skip cloning and check out the pinned revision
after preserving any local changes. Download only English with `--language en`, or only
the Vietnamese source assets with `--language vi`. Running the downloader without
`--download-assets` performs no network access. Vietnamese conversion runs the official
export wrappers with PyTorch's legacy ONNX exporter, separate processes per component,
and safe tensor-only checkpoint loading. Run conversion before starting model workers on
a machine with limited RAM. Its extra `onnx`/`tensorboard` dependencies are export tools,
not required by the running API.

The prepared graphs use the example paths `models/runtime/tts/{vi,en}/zipvoice/`, mono
24 kHz audio, and the 100-bin `vocos_24khz.onnx` vocoder. The direct tokenizer uses data
bundled with `espeakng-loader`; legacy `data_dir`/`lexicon` options remain parseable but
are not required by this runtime. The scripts save upstream model cards, pinned source
revisions, and SHA256 manifests alongside the ignored model assets. The Vietnamese
source checkpoint stays under `models/source/tts/vi/zipvoice/`.

These two downloads are different checkpoints with different model licenses:

- English: [k2-fsa/ZipVoice](https://huggingface.co/k2-fsa/ZipVoice), revision
  `889dd609a42f0de9cf9aac335eae42677becb1b9`; its model card specifies CC-BY-NC due
  to the Emilia training data. The upstream implementation code is Apache-2.0.
- Vietnamese: the originating author's [hynt/ZipVoice-Vietnamese-2500h](https://huggingface.co/hynt/ZipVoice-Vietnamese-2500h),
  revision `d9792210a42a5d001843930f5cfabc1fe4e15407`, CC-BY-NC-SA-4.0;
  `iter-525000-avg-2.pt` is locally exported with the official ZipVoice architecture.
- Vocos: the [official Sherpa ONNX release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/vocoder-models)
  of [charactr/vocos-mel-24khz](https://huggingface.co/charactr/vocos-mel-24khz), MIT;
  the downloader checks the release asset's published SHA256.

This setup is for local research/integration testing. The application license does not
replace model or training-data terms. No ASR weights are downloaded by these commands.

### VieNeu TTS v3 Turbo

```powershell
# SDK only, in .venv-vieneu; does not download model weights:
.\.venv\Scripts\python.exe scripts/setup_vieneu.py

# Explicitly fetch the main model, codec and text frontend assets when wanted:
.\.venv\Scripts\python.exe scripts/setup_vieneu.py --skip-install --download-assets
```

The installer pins `vieneu==3.8.3`. Its environment is separate from the API's Torch,
ONNX Runtime and phonemizer versions. Use `--environment-dir` and `--model-root` for
alternative directories, then update the profile paths to match. See `--help`.
The default downloads pin the exact snapshots validated with this adapter:

- `pnnbao-ump/VieNeu-TTS-v3-Turbo` at `61b85e3d937fbbacb387714180e8182823512523`.
- `OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX` at
  `ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae`.

Explicit `--model-revision` and `--codec-revision` overrides require full commit
SHAs. After downloading, the script verifies required files and records source
revisions, file sizes and SHA256 checksums in `<model-root>/manifest.json`.
SDK 3.8.3 resolves the codec through `main`, so the script atomically points that
alias at the verified pinned snapshot inside this profile's managed cache. It does
not change the user's global Hugging Face cache.

This adapter uses the SDK's ONNX CPU fp32 path and returns mono float32 audio at
48 kHz. The worker sets its Hugging Face cache and offline flags before importing
the SDK. This matters because the public SDK does not pass a local codec directory
through its constructor: the codec must exist in the prepared cache. The API process
never changes its own environment variables to switch models.

The worker loads lazily, persists across requests, serializes inference per profile,
uses bounded load/inference timeouts, and is closed on application shutdown. Reference
and output transfer files are temporary and removed after each request. The current
adapter does not support GPU, `num_steps`, speed adjustment, presets, or streaming;
these require explicit adapter capability/workflow extensions. Unsupported step/speed
overrides are rejected rather than silently ignored by the SDK.

## API and UI

- `GET /api/v1/tts/models` returns the catalog, language defaults, capabilities,
  dependency/asset checks, and status of each profile without loading models.
- TTS synthesis/job creation forms accept optional `model_id`; omitted IDs use the
  language's configured default. Responses and saved jobs include `model_id`.
- `POST /warmup/tts?model_id=vieneu-v3-turbo&language=vi` warms that profile.
- `/warmup` and startup warmup load unique default profiles only. A missing optional
  alternative does not block the defaults.
- `/readyz` checks enabled ASR plus default TTS profiles and storage. The model catalog
  shows missing optional profiles independently. File/dependency readiness is not a
  guarantee of valid model tensors; successful warmup/inference is the runtime check.

Studio Generate selects the TTS model independently of language and only shows controls
the selected adapter supports. Settings displays each model separately. Jobs retain and
display their model identity, and reruns send that identity explicitly.

## Adding another TTS engine

1. Implement `TtsAdapter` in `inference/tts/`. Keep `checks()` free of model imports,
   downloads, and inference. Constructors must not load weights.
2. Declare actual reference-audio, step-count and speed capabilities. Implement
   `load`, `synthesize`, and `close`; return finite mono audio at the profile sample rate.
3. Register the factory in `default_registry()`. Arbitrary Python import strings are
   deliberately not accepted from configuration.
4. Add a profile and explicit language defaults if it should be the default. Install
   optional dependencies in the API environment only when compatible; otherwise use
   an isolated worker similar to VieNeu.
5. Test routing, capability rejection, missing assets, initialization failure,
   concurrency, cleanup, and exact sample-rate propagation. The shared reference-voice
   workflow requires no new router/job implementation for another compatible engine.

An engine requiring a different input contract (presets only, prompts, text-to-music)
needs a deliberate workflow/schema extension; do not force its inputs into ZipVoice
fields. ASR and realtime recognition remain separate capabilities and should get their
own adapter contract when another recognition engine is introduced.

## Verification and upstream references

`tests/test_tts_registry.py`, `tests/test_tts_model_jobs.py`, and
`tests/test_vieneu_adapter.py` cover routing, legacy migration, idempotency, isolation
and worker lifecycle without weights. Browser QA includes `qa-models.mjs` for model
switching, capabilities and request identity. These tests do not establish perceptual
quality or real-model compatibility on this machine; run warmup and an audio smoke
after installing compatible weights.

Use a real reference recording and its transcript for the integration smoke:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_tts_model.py --model-id vieneu-v3-turbo --language vi --reference-wav reference.wav --reference-text-file reference.txt --text "Xin chào, đây là bản kiểm tra giọng nói." --output-dir tmp/model-smoke
```

The command warms the selected model, creates a saved voice and queued job, checks
idempotent replay, downloads the WAV, and writes a JSON report with timings and
audio metrics. It retains the records so they can be inspected in Studio. Use
`--voice-id` from that report to reuse the same reference with `--model-id zipvoice-vi`.
Pass `--acknowledge-warnings` only after reviewing the reference intake warnings.
The waveform checks establish valid, non-silent output; listening is still needed
to judge pronunciation and voice quality. Do not use the synthetic sine reference
from the older infrastructure smoke script to assess a real voice-cloning model.

Verified integration sources:

- [VieNeu SDK overview](https://docs.vieneu.io/docs/sdk/overview/)
- [VieNeu 3.8.3 package](https://pypi.org/project/vieneu/3.8.3/)
- [Official v3 Turbo implementation](https://github.com/pnnbao97/VieNeu-TTS/blob/85344322b7258b4e25479b692e8e3396baf9db34/src/vieneu/v3turbo.py)
- [Official ONNX implementation](https://github.com/pnnbao97/VieNeu-TTS/blob/85344322b7258b4e25479b692e8e3396baf9db34/src/vieneu/_v3_turbo_engine/onnx_runtime_lite.py)

Application licensing does not replace the licenses/notices for model weights, SDKs,
codecs, or reference recordings.
