# VassilStudio

[![Quality](https://github.com/linhlln1104/VassilStudio/actions/workflows/quality.yml/badge.svg)](https://github.com/linhlln1104/VassilStudio/actions/workflows/quality.yml)

VassilStudio is a modular monolith for local voice workflows built around ZipFormer ASR and ZipVoice TTS models in `models/runtime/`.

The upstream runtime foundation is cloned locally at `foundation/sherpa-onnx` for reference. VassilStudio itself stays rooted in this repository and uses `sherpa-onnx` for ZipFormer ASR plus a direct ONNX runtime path for ZipVoice TTS.

See `CHANGELOG.md` for productionization milestones.
See `docs/operations.md` for install, model layout, auth, smoke, Docker, backup, and troubleshooting.

## Current Shape

- `backend/vvoice/domains/asr`: language-aware ZipFormer transcription.
- `backend/vvoice/domains/tts`: ZipVoice zero-shot speech generation.
- `backend/vvoice/domains/voices`: reference voice profile storage.
- `backend/vvoice/domains/realtime`: websocket chunked ASR for live microphone workflows.
- `backend/vvoice/shared/audio`: shared audio decode, resample, and WAV encoding.
- `backend/vvoice/shared/security`: API key, Studio session, and WebSocket auth helpers.
- `backend/vvoice/app/auth`: local owner account and session endpoints.
- `backend/vvoice/app/studio`: public product shell and Studio static UI route.
- `backend/vvoice/app/system`: health, model status, and warmup routes.
- `backend/vvoice/main.py`: FastAPI composition through routers.
- `frontend/studio-react`: production React Studio UI served by the backend from `/studio`.
- `frontend/studio`: legacy static Studio kept as a fallback during the transition.

See `docs/source-layout.md` for the DeerFlow-inspired workspace direction.

## Important Model Note

ASR models are selected by language through `asr.models` in `config/vassil.example.json`. The default
profile is `asr.models.vi`, and `asr.models.en` enables the local English ZipFormer assets for direct
transcription and reference transcript generation.

TTS models are selected by language through `tts.models` in `config/vassil.example.json`. The default
profile is `tts.models.vi`, and `tts.models.en` enables the local English ZipVoice assets. Keep the
voice profile language aligned with the text you generate so English text uses the English tokenizer
and Vietnamese text uses the Vietnamese tokenizer.

ZipVoice models are trained with eSpeak tokenizers. VassilStudio phonemizes text and reference transcripts
with `phonemizer-fork` and the bundled `espeakng-loader` runtime, maps those symbols directly into
each ZipVoice `tokens.txt`, and runs the ZipVoice ONNX models directly. This keeps clean Windows and
Docker installs reproducible without a separately built phonemizer wheel.

Studio, batch ASR jobs, realtime ASR, voice import, and TTS jobs all carry an explicit `language`
field. Use `vi` for Vietnamese and `en` for English so the backend selects the matching tokenizer,
ASR recognizer, and ZipVoice runtime.

`VassilStudio` is the display name. Before ZipVoice phonemization, the backend expands that token to
`Vassil Studio` so generated speech treats the brand as two pronounceable words.

The existing `vocoder.onnx` from the ZipVoice drop is a 22.05 kHz / 80-mel Vocos model and does not match this ZipVoice model, which emits 100-bin mel features. Use the 24 kHz Vocos model:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\download_vocoder.ps1
```

## Storage Layout

- `models/runtime`: model files used by the app. Mounted read-only in Docker.
- `models/source`: original exports, checkpoints, and legacy drops kept for traceability.
- `data/voices`: saved voice profiles and loose voice import candidates.
- `data/jobs/asr`: asynchronous ASR job state and normalized input audio.
- `data/jobs/tts`: asynchronous TTS job state and generated job WAV files.
- `data/uploads`: reserved for future upload staging.
- `data/outputs`: reserved for exported audio.
- `logs`: runtime logs.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_storage.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\download_vocoder.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_api.ps1
```

The API starts on `http://127.0.0.1:8000`.

Build the React Studio before serving `/studio` from a local source checkout:

```powershell
cd frontend\studio-react
npm.cmd install
npm.cmd run build
cd ..\..
```

Open the local product shell and Studio:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/studio
```

## Runtime Tuning

Queued ASR and TTS jobs are serialized by default for predictable CPU performance. On stronger
hardware, increase the worker limits in `config/vassil.example.json`:

```json
"runtime": {
  "environment": "local",
  "log_level": "INFO",
  "provider": "cpu",
  "num_threads": 2,
  "debug": false,
  "warmup_on_startup": false
},
"jobs": {
  "asr_max_workers": 1,
  "tts_max_workers": 1,
  "asr_max_attempts": 1,
  "tts_max_attempts": 1,
  "retry_backoff_seconds": 0.5
},
"limits": {
  "max_upload_bytes": 52428800,
  "max_tts_text_chars": 5000,
  "max_reference_text_chars": 2000,
  "max_voice_name_chars": 120,
  "max_realtime_frame_bytes": 2097152
}
```

Model inference still uses per-language locks, so increasing workers mostly improves queue handling
around IO and mixed ASR/TTS work. Test with `scripts/check.ps1 -RunLanguageMatrix` after changing it.
Jobs support cooperative cancellation and retry metadata. Queued jobs cancel immediately; running jobs
move through `cancelling` and stop at the next safe point around decode/model/output work. Retry is
disabled by default with one attempt; raise `asr_max_attempts` or `tts_max_attempts` only after testing
latency and CPU pressure on the target machine.

Use Settings -> Warm models or call `/warmup` to load all configured ASR/TTS languages before a
session. Set `runtime.warmup_on_startup` to `true` only when slower startup is acceptable and you want
the first ASR/TTS request to avoid model-load latency.

The Generate view includes Preview and Production render modes; Preview uses fewer ZipVoice steps for
faster drafts, while Production uses the configured default-quality path. API callers can pass
`num_steps` from `1` to `64` and `speed` from `0.5` to `2.0`.

## Health And Observability

Use `/livez` for process liveness and `/readyz` for model/storage readiness. `/health` remains a
stable compatibility endpoint for the Studio and older scripts, while `/model-status` returns detailed
model file checks and runtime state.
Settings also shows local storage usage from `/diagnostics` and can clean terminal ASR/TTS jobs by
retention window without touching active jobs.

Every HTTP response includes `X-Request-ID`. Clients may send their own `X-Request-ID`; otherwise the
server generates one. Application logs are structured JSON under the `vvoice` logger and include
request IDs for HTTP requests plus job IDs for ASR/TTS job lifecycle events. API keys and query strings
are not logged by the app request middleware.

## Verify

Run the default project quality gate:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

The default check runs storage setup, doctor, OpenAPI export, ruff, pytest, React Studio
lint/build, legacy frontend JavaScript syntax checks, and Docker Compose config validation.
GitHub Actions runs the Windows CI equivalent with `scripts/check.ps1 -CI`; that mode performs a
clean npm install, rejects high-severity npm advisories and generated OpenAPI drift, and leaves
model-binary and Docker-daemon validation to the release hardware gates below.
Optional runtime checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunE2E
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunLanguageMatrix
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunDocker
```

Latency benchmarks run against a live API and write JSON summaries under `tmp/benchmarks`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_tts_latency.ps1 --iterations 1 --num-steps 8
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_asr_latency.ps1 --iterations 3
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_realtime_chunking.ps1 --chunks 5
```

## Docker

Docker builds the React Studio assets and the VassilStudio app, then mounts local models at runtime:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_docker.ps1
```

Run a disposable Docker smoke check without taking over port 8000:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_docker.ps1
```

The compose service mounts:

- `./models` -> `/app/models` read-only
- `./config` -> `/app/config` read-only
- `./data` -> `/app/data` writable
- `./logs` -> `/app/logs` writable

## Studio Local Auth And API Keys

Studio account auth is disabled by default for local development. To require a browser login for
`/studio`, copy `.env.example` or set:

```powershell
$env:VASSIL_AUTH_REQUIRED="true"
$env:VASSIL_SESSION_SECRET = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Startup rejects auth-enabled configurations with missing, short, or documented placeholder session
secrets. Use `VASSIL_ENV=production` only behind HTTPS; that profile also requires auth, secure
cookies, and debug mode off. Native loopback installs normally use `local`, while Compose defaults
to `docker`.

`scripts/run_api.ps1` loads `.env` automatically for native local runs while preserving any
environment variables already set in the shell.

On the first browser visit, `/studio` redirects to `/setup`. Setup creates one local owner account in
`data/auth.sqlite3` and stores only a password hash. Browser sessions use an HttpOnly cookie. Logout
invalidates the server-side session. Settings can change the local owner password and revoke other
active sessions. Repeated failed login and password change attempts are locally rate-limited.

API key auth remains available for automation and smoke scripts. Enable it by adding keys to
`config/vassil.example.json`:

```json
"security": {
  "api_keys": ["change-me"],
  "auth_required": true
}
```

Or set keys by environment variable:

```powershell
$env:VASSIL_API_KEYS="change-me,another-key"
```

Clients can authenticate with either header:

```text
X-Vassil-API-Key: change-me
Authorization: Bearer change-me
```

For smoke scripts, set:

```powershell
$env:VASSIL_API_KEY="change-me"
```

Legacy `VVOICE_*` environment variables and `X-VVoice-API-Key` are still accepted for existing local setups.

`/health` and `/livez` remain public for health checks. Protected API routes accept either a valid
Studio session cookie or a configured API key.

## API Slice

```powershell
Invoke-WebRequest http://127.0.0.1:8000/livez
Invoke-WebRequest http://127.0.0.1:8000/readyz
Invoke-WebRequest http://127.0.0.1:8000/health
Invoke-WebRequest http://127.0.0.1:8000/model-status
Invoke-WebRequest http://127.0.0.1:8000/diagnostics
Invoke-WebRequest http://127.0.0.1:8000/diagnostics/bundle -OutFile diagnostics.zip
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export_openapi.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_auth.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_api.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_voices.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_asr.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_asr_job.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_realtime.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_tts_job.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_language_matrix.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_e2e_sample_voice.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_cleanup_jobs.ps1
```

Preload ASR/TTS runtimes:

```powershell
Invoke-WebRequest -Method Post http://127.0.0.1:8000/warmup
```

Run an end-to-end TTS smoke test. It creates a synthetic reference WAV, stores a temporary voice profile, synthesizes a WAV, and writes it to `tmp/smoke/generated.wav`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_tts.ps1
```

Run the real Vietnamese E2E smoke test with `data/voices/sample voice.weba`. It imports the loose
candidate voice, auto-transcribes the reference audio, queues a TTS job, and writes output to
`data/outputs/sample-voice-e2e.wav`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_e2e_sample_voice.ps1
```

Create a reusable voice profile:

```powershell
Invoke-WebRequest `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/voices `
  -Form @{
    name = "demo"
    reference_text = "xin chao"
    reference_audio = Get-Item ".\reference.wav"
  }
```

Create a voice profile and let VassilStudio transcribe the reference audio:

```powershell
Invoke-WebRequest `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/voices `
  -Form @{
    name = "demo-auto"
    auto_transcribe = "true"
    reference_audio = Get-Item ".\reference.wav"
  }
```

Synthesize with a saved voice:

```powershell
Invoke-WebRequest `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/tts/synthesize/voices/<voice_id> `
  -Form @{ text = "xin chao, day la VassilStudio"; num_steps = 16 } `
  -OutFile generated.wav
```

Queue an asynchronous TTS job with a saved voice:

```powershell
$job = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/tts/jobs/voices/<voice_id> `
  -Form @{ text = "xin chao, day la VassilStudio"; language = "vi"; num_steps = 16 }

Invoke-RestMethod http://127.0.0.1:8000/api/v1/tts/jobs/$($job.job_id)
Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/api/v1/tts/jobs/$($job.job_id)/audio `
  -OutFile generated.wav
```

Clean finished TTS jobs:

```powershell
Invoke-RestMethod -Method Delete http://127.0.0.1:8000/api/v1/tts/jobs
Invoke-RestMethod -Method Delete http://127.0.0.1:8000/api/v1/tts/jobs?max_age_seconds=86400
```

Cancel an active TTS job:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/tts/jobs/<job_id>/cancel
```

Download or preview the saved reference audio:

```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/api/v1/voices/<voice_id>/reference-audio `
  -OutFile reference.wav
```

Update a saved voice profile without replacing the reference audio:

```powershell
Invoke-WebRequest `
  -Method Patch `
  -Uri http://127.0.0.1:8000/api/v1/voices/<voice_id> `
  -Form @{ name = "demo-fixed"; reference_text = "xin chao da sua" }
```

Queue an asynchronous ASR job:

```powershell
$job = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/asr/jobs `
  -Form @{ language = "vi"; audio = Get-Item ".\audio.wav" }

Invoke-RestMethod http://127.0.0.1:8000/api/v1/asr/jobs/$($job.job_id)
```

Clean finished ASR jobs:

```powershell
Invoke-RestMethod -Method Delete http://127.0.0.1:8000/api/v1/asr/jobs
Invoke-RestMethod -Method Delete http://127.0.0.1:8000/api/v1/asr/jobs?max_age_seconds=86400
```

Cancel an active ASR job:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/asr/jobs/<job_id>/cancel
```

Realtime ASR websocket:

```text
ws://127.0.0.1:8000/api/v1/realtime/asr?language=vi
```

Protocol summary:

- Server sends `{"type":"ready","language":"vi", ...}` after accepting the socket.
- Client may send `{"type":"config","sample_rate":16000,"encoding":"pcm_f32le"}`.
- Client streams mono PCM binary chunks. Supported encodings are `pcm_f32le` and `pcm_s16le`.
- Server returns `{"type":"transcript","text":"...", ...}` per chunk.
- Client can send `{"type":"flush"}`, `{"type":"clear"}`, or `{"type":"close"}`.

## Foundation

The source reference clone is intentionally not the app root:

```text
foundation/sherpa-onnx/
```

Use it to inspect official examples, especially:

- `python-api-examples/offline-decode-files.py`
- `python-api-examples/zipvoice-tts.py`
- `python-api-examples/vad-with-non-streaming-asr.py`
