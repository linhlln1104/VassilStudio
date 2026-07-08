# VassilStudio Architecture

VassilStudio is designed as a modular monolith. It runs as one process, but the code is split by business capability so each module can be tested, owned, and eventually extracted independently.

## Dependency Direction

```text
HTTP routers -> module services -> runtime adapters -> sherpa-onnx / filesystem
             -> shared audio utilities
```

Routers translate HTTP details into application calls. Module services own use cases. Runtime adapters are kept inside modules so model-specific decisions do not leak across the app.

## Modules

### ASR

`backend/vvoice/domains/asr`

Uses ZipFormer via `sherpa_onnx.OfflineRecognizer.from_transducer`. Runtime selection is
language-aware through `asr.models`, currently with Vietnamese and English profiles. The current
models are non-streaming ZipFormer variants, so realtime UX uses chunking rather than true streaming
transducer state.

The module exposes direct transcription and filesystem-backed async jobs under `/api/v1/asr/jobs`.
Jobs store normalized input WAV files and transcript metadata under `data/jobs/asr`, then run through
a single-worker queue to avoid concurrent recognizer pressure.
Terminal ASR jobs can be cleaned with `DELETE /api/v1/asr/jobs`, optionally filtered by
`max_age_seconds`.
ASR jobs use a small lifecycle state machine: `queued`, `running`, `cancelling`, `succeeded`,
`failed`, and `cancelled`. `POST /api/v1/asr/jobs/{job_id}/cancel` cancels queued work immediately
and asks running work to stop at the next safe point. Retry metadata is stored with each job as
`attempt`, `max_attempts`, `failed_reason`, and `cancel_requested`.

### TTS

`backend/vvoice/domains/tts`

Uses ZipVoice via `sherpa_onnx.OfflineTtsZipvoiceModelConfig`.

TTS runtime selection is language-aware. `config/vassil.example.json` defines `tts.models.vi` as the
default Vietnamese ZipVoice profile and `tts.models.en` as the English profile, each with its own
tokens, encoder, decoder, vocoder, and frontend data directory. The service lazy-loads one ZipVoice
runtime per configured language and rejects unconfigured languages before queueing jobs, so English
text cannot accidentally run through Vietnamese model assets.

ZipVoice models use eSpeak tokenizers. VassilStudio phonemizes generation text and reference transcripts
in `backend/vvoice/domains/tts/text_frontend.py` before handing them to the direct ONNX runtime path.
This avoids sending one language through another language's text frontend, which can produce
voice-like audio without intelligible words.

Model mapping:

- `encoder`: `text_model.onnx`
- `decoder`: `flow_matching_model.onnx`
- `vocoder`: `vocos_24khz.onnx`

The bundled `vocoder.onnx` is 22.05 kHz / 80-mel and does not match this ZipVoice model's 100-bin features.

The module exposes both direct request-response synthesis and filesystem-backed async jobs under
`/api/v1/tts/jobs`. Jobs store JSON metadata and generated WAV files under `data/jobs/tts`, while
execution stays in-process through a single-worker queue so ZipVoice does not run multiple expensive
generations at once.
Terminal TTS jobs can be cleaned with `DELETE /api/v1/tts/jobs`, optionally filtered by
`max_age_seconds`.
TTS jobs use the same lifecycle contract as ASR jobs. `POST /api/v1/tts/jobs/{job_id}/cancel`
cancels queued work immediately and prevents a running generation from writing output if cancellation
is requested before the final output step.

### Voices

`backend/vvoice/domains/voices`

Stores reusable voice references: normalized WAV audio, transcript, and metadata. The first implementation is filesystem-based under `data/voices`.

### Audio

`backend/vvoice/shared/audio`

Centralized audio decode, resample, mono conversion, and WAV encoding.
Routers read uploads through shared validation helpers so request size limits are enforced before
decode/resample work begins.

### Realtime

`backend/vvoice/domains/realtime`

Owns websocket boundaries and chunk/session state. The first implementation accepts mono PCM
binary frames, buffers them into fixed-duration chunks, skips low-RMS silence, and calls the ASR
service through the application container. The websocket accepts `language=vi|en` in the query string
and returns the selected language in `ready` and `transcript` messages. It does not construct model
runtimes directly.

Future VAD or streaming model work should stay inside this module and continue to call ASR through
the existing service boundary.

### Security

`backend/vvoice/shared/security`

Owns API credential checks for HTTP and WebSocket boundaries. Protected APIs accept either a valid
Studio session cookie or an API key. HTTP clients can use `X-Vassil-API-Key` or
`Authorization: Bearer`; browser WebSocket clients can pass `api_key` in the query string or rely on
the Studio session cookie. Legacy `X-VVoice-API-Key` is still accepted.

### Local Auth

`backend/vvoice/app/auth`

Owns local-first browser account setup and session lifecycle. When `security.auth_required` or
`VASSIL_AUTH_REQUIRED` is enabled, `/studio` redirects to `/setup` until a local owner account exists,
then to `/login` until the browser has a valid session. Accounts and server-side sessions are stored
in a small SQLite database at `security.auth_db_path`, defaulting to `data/auth.sqlite3`. Passwords
are hashed with PBKDF2-HMAC-SHA256. Session cookies are HttpOnly and can be configured with
`security.session_cookie_name`, `security.session_ttl_seconds`, and `security.secure_cookies`.

API key auth remains available for smoke scripts and automation even when Studio auth is required.

### Product Shell

`backend/vvoice/app/studio`

Serves the public product shell at `/`, auth screens at `/setup` and `/login`, support/trust pages,
and the Studio app at `/studio`. Static file lookup resolves paths inside the built Studio directory
before serving files so traversal attempts do not escape the asset root.

### Observability

`backend/vvoice/core/observability.py`

HTTP requests receive an `X-Request-ID` response header. Clients can provide this header or let the
server generate one. The app logger emits structured JSON for HTTP request completion/failure and
ASR/TTS job lifecycle events. Request logging records the path without query strings so API keys are
not written by the app middleware.

## Current Use Cases

- Upload audio and transcribe it with `/api/v1/asr/transcribe`.
- Queue long-running transcription with `/api/v1/asr/jobs`.
- Cancel active transcription jobs with `/api/v1/asr/jobs/{job_id}/cancel`.
- Clean terminal transcription jobs with `DELETE /api/v1/asr/jobs`.
- Generate one-off speech with `/api/v1/tts/synthesize`.
- Create/list/get/delete voice profiles with `/api/v1/voices`.
- Create a voice profile with ASR-derived `reference_text` by posting `auto_transcribe=true`.
- Generate speech from a stored profile with `/api/v1/tts/synthesize/voices/{voice_id}`.
- Queue long-running speech generation with `/api/v1/tts/jobs/voices/{voice_id}`.
- Cancel active speech jobs with `/api/v1/tts/jobs/{job_id}/cancel`.
- Clean terminal speech jobs with `DELETE /api/v1/tts/jobs`.
- Stream microphone PCM to `/api/v1/realtime/asr?language=vi` and receive chunked transcripts.
- Require API keys for model/voice/job APIs when `security.api_keys` or `VASSIL_API_KEYS` is set.
- Require browser login for Studio and protected APIs when `security.auth_required` or
  `VASSIL_AUTH_REQUIRED` is set.
- Preload lazy ASR/TTS runtimes with `/warmup`, `/warmup/asr`, and `/warmup/tts`.
- Check process liveness with `/livez` and model/storage readiness with `/readyz`.

## Configuration

Runtime config is JSON in `config/vassil.example.json`. For local overrides, copy it to `config/vassil.local.json` or set:

```powershell
$env:VASSIL_CONFIG="C:\path\to\vassil.local.json"
```

Legacy `config/vvoice.example.json`, `VVOICE_CONFIG`, `VVOICE_ROOT`, and `VVOICE_API_KEYS` remain supported for existing setups.

The `limits` section centralizes request boundaries for uploaded audio, TTS text, reference
transcripts, voice profile names, and realtime WebSocket frame size.

## Deployment Shape

The Docker image contains only the application code and Python runtime dependencies. Model assets stay
outside the image and are mounted into `/app/models` so image rebuilds stay fast and deployment can
swap model folders independently from code.

Persist `/app/data` when using voice profiles, because the filesystem voice store writes normalized
reference WAV files, job metadata, and generated job artifacts there. Persist `/app/logs` if runtime
logs are written by the deployment environment.

## Production Notes

- Keep model objects as singletons per process; loading them per request is too expensive.
- Prefer CPU int8 for small machines and CUDA provider only with a compatible sherpa-onnx wheel.
- Add queueing around ZipVoice if concurrency rises; flow matching can saturate CPU quickly.
- Keep the Vietnamese phonemizer health check in `scripts/doctor.py`; text frontend regressions are
  easier to catch there than by listening to generated WAVs after the fact.
