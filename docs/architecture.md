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
When sherpa-onnx returns token or native segment timestamps, ASR persists stable timed segments beside
the immutable raw model text. The editable transcript is stored separately with an optimistic revision
number, so correction never destroys the original recognition result. Existing metadata without this
contract loads as an untimed revision-zero transcript.
Terminal ASR jobs can be cleaned with `DELETE /api/v1/asr/jobs`, optionally filtered by
`max_age_seconds`.
ASR jobs use a small lifecycle state machine: `queued`, `running`, `cancelling`, `succeeded`,
`failed`, and `cancelled`. `POST /api/v1/asr/jobs/{job_id}/cancel` cancels queued work immediately
and asks running work to stop at the next safe point. Retry metadata is stored with each job as
`attempt`, `max_attempts`, `failed_reason`, and `cancel_requested`.
`POST /api/v1/asr/jobs` accepts an optional `Idempotency-Key`. The service stores a digest of the key
and a fingerprint of language, source name, and audio content. A replay with the same request returns
the existing job; reusing the key for different content returns `409`.
`PATCH /api/v1/asr/jobs/{job_id}/transcript` updates either all timed segment texts or one untimed text
body and requires `expected_revision`; stale writers receive `409`. Transcript exports are available at
`GET /api/v1/asr/jobs/{job_id}/exports/{format}` for `txt`, `srt`, `vtt`, and `json`. Subtitle formats
require persisted model timing. JSON includes current and raw transcript state for traceability.

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
`POST /api/v1/tts/jobs/voices/{voice_id}` supports the same idempotency contract, fingerprinting the
validated voice, text, language, steps, and speed. TTS writes to `output.wav.tmp`, then atomically
promotes the file only inside the lock-protected success transition.

Both job responses expose a non-percent progress contract through `progress_stage` and
`stage_started_at`. Stages are `queued`, `preparing_input`, `running_model`, `finalizing`,
`retry_wait`, and terminal states. `cancellation_mode` is currently `safe_point`: a blocking model
call is allowed to return before cancellation becomes terminal, so the UI says `Stopping` and keeps
showing the actual stage instead of promising immediate interruption.

### Voices

`backend/vvoice/domains/voices`

Stores reusable voice references as normalized WAV audio, transcript, content hash, and metadata under
`data/voices`. Intake is a stateless analyze/review/commit workflow: upload bytes stay in the browser
and loose local files stay in the workspace until commit. Analysis measures source format, selected
duration, silence, clipping, and energy-based speech coverage; it also proposes trim boundaries and
checks transcript/language compatibility. Commit repeats decode and validation, verifies the reviewed
source hash, and rejects duplicate canonical audio while holding the voice-store lock. Metadata version
4 adds `audio_sha256`; legacy profiles remain readable and are hashed lazily during duplicate checks.

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
are hashed with scrypt-SHA256 for new accounts, while legacy PBKDF2-HMAC-SHA256 hashes remain
verifiable for existing local databases. Session cookies are HttpOnly and can be configured with
`security.session_cookie_name`, `security.session_ttl_seconds`, and `security.secure_cookies`.

API key auth remains available for smoke scripts and automation even when Studio auth is required.
The browser always prefers a valid owner session and does not attach a temporary API key while that
session is active. Browser-entered keys live in module memory by default, can be retained only in the
current tab with `sessionStorage`, and are cleared on logout. Startup code removes retired
`localStorage` key entries instead of migrating them.

Protected audio is not bound directly to a media URL when Jobs renders playback. The React media
component fetches through the same authenticated client as JSON requests, creates a revocable
`blob:` URL, and uses that local URL for playback and download. This keeps temporary API keys in
request headers and avoids query credentials or unauthenticated native-media requests.

The HTTP middleware applies a restrictive Content Security Policy and standard browser protections
to every response. Studio HTML receives a cryptographically random nonce per response; the React
entry point passes it to Radix's runtime style helper so dynamic modal styles remain CSP-authorized
without enabling arbitrary inline style elements. Auth responses disable caching, and HTTPS
responses enable HSTS. The connect policy derives the WebSocket source from the validated request
host so realtime traffic cannot target an unrelated origin; nonced Studio HTML is never cached.

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
not written by the app middleware. The application disables Uvicorn's access logger because its raw
request line includes query strings; native and Docker launchers enforce the same setting.

`GET /diagnostics` returns privacy-filtered operations metadata for the Studio Settings surface and
support workflows: runtime configuration, auth mode, logical storage aliases with bucketed inventory
and disk values, and local open-source license metadata.
`GET /diagnostics/bundle` packages the same metadata with readiness JSON and an environment manifest.
Host metadata is excluded unless the caller explicitly sets `include_host_metadata=true`; even then,
only the Python version, OS family/release, and architecture are added. Diagnostics do not return API
keys, session secrets, cookies, transcripts, or audio content, and archives must be reviewed before
sharing.

## Current Use Cases

- Upload audio and transcribe it with `/api/v1/asr/transcribe`.
- Queue long-running transcription with `/api/v1/asr/jobs`.
- Cancel active transcription jobs with `/api/v1/asr/jobs/{job_id}/cancel`.
- Correct a completed transcript with `/api/v1/asr/jobs/{job_id}/transcript`.
- Export a completed transcript with `/api/v1/asr/jobs/{job_id}/exports/{format}`.
- Clean terminal transcription jobs with `DELETE /api/v1/asr/jobs`.
- Generate one-off speech with `/api/v1/tts/synthesize`.
- Create/list/get/delete voice profiles with `/api/v1/voices`.
- Review uploads with `/api/v1/voices/intake/analyze` and loose files with
  `/api/v1/voices/import-candidates/{filename}/analyze` before committing them.
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
- Inspect privacy-filtered runtime/auth/storage/license metadata with `/diagnostics`.
- Download a privacy-filtered support zip with `/diagnostics/bundle`.
- Review storage usage and clean terminal ASR/TTS jobs from Settings.

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
