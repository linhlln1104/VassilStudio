# VassilStudio end-to-end product audit

- Date: 2026-08-24
- Audited commit: `894ccb2`
- Environment: Windows 11, Python 3.12.10, Node 24.18.1, CPU inference
- Surfaces: public product pages, first-run setup, authentication, Studio workflows, REST/WebSocket APIs, responsive layouts, and quality gates
- Audit-time release decision: **NO-GO for Docker or any non-loopback exposure; usable for controlled localhost development**
- P0 remediation status: **RESOLVED AND VERIFIED on 2026-08-24**
- Diagnostics privacy P1 status: **RESOLVED AND VERIFIED on 2026-08-24**
- Browser security P1 status: **RESOLVED AND VERIFIED on 2026-08-24**
- Jobs playback P1 status: **RESOLVED AND VERIFIED on 2026-08-24**

## P0 remediation update

- Docker Compose and the native launcher now default to `127.0.0.1`; Compose records the same
  effective bind address inside the container, while a direct image run fails closed.
- Startup rejects anonymous non-loopback binds. Owner-auth deployments must complete first-owner
  setup on loopback before they can move to a LAN address.
- Audio uploads are rejected before decoding unless extension, declared MIME type, and container
  signature agree with the supported format allowlist.
- HTTP, queued-job, realtime, and Voice response boundaries no longer expose raw decoder commands,
  model paths, legacy job errors, or voice storage paths.
- Verification passed with `scripts/check.ps1` (`142 passed`, Ruff, React lint/build, OpenAPI,
  auth smoke, Compose validation), a clean Docker image/runtime smoke on `127.0.0.1:8024`, and a
  live invalid-upload probe returning stable HTTP `415` with no workspace or FFmpeg detail.

The remaining P1/P2 findings still require follow-up before a broader production release. The P0
section above closes only the Security Boundary gate; the focused P1 closure follows below.

## P1 diagnostics privacy remediation update

- `/diagnostics` now returns fixed logical storage aliases, bucketed usage/file-count/disk values,
  and storage pressure instead of host paths or exact inventory.
- Support bundles exclude Python/OS/architecture metadata by default. The Settings control and API
  query require an explicit opt-in for each bundle that includes coarse host metadata.
- Bundle and public product copy now require review before sharing and no longer claim unconditional
  sharing safety.
- Regression coverage scans the default archive for workspace paths and host fields. Verification
  passed with `scripts/check.ps1` (`143 passed`, Ruff, React lint/build, OpenAPI, auth smoke, Compose
  validation), live default/opt-in archive probes, and Settings Playwright QA at desktop/mobile.

## P1 browser security remediation update

- Studio now prefers the HttpOnly owner session and suppresses the temporary API-key header whenever
  that session is active.
- Browser-entered automation keys remain in memory by default. Operators can explicitly retain one
  only in the current tab with `sessionStorage`; retired `localStorage` entries are scrubbed.
- Settings clears the input after activation, no longer offers post-save copy, and clears temporary
  credentials on logout.
- Responses now carry a restrictive CSP, per-response style nonce, frame/MIME/referrer/opener and
  permissions protections, same-origin-only WebSockets, no-store nonce HTML/auth caching, and
  HTTPS-only HSTS.
- Uvicorn access logs are disabled across application/native/Docker launch paths so browser
  WebSocket query credentials cannot be persisted; structured request logs remain query-free.
- Verification passed with `scripts/check.ps1` (`147 passed`, Ruff, React lint/build, OpenAPI, auth
  smoke, Compose validation), live header/CSP probes, and Settings Playwright credential regression
  QA at desktop/mobile.

## Executive summary

The main workflows work: a local owner can sign in, manage a voice profile, render speech, transcribe audio, inspect jobs, use realtime ASR, and inspect runtime health. The visual system is consistent and responsive, and the automated baseline is healthy.

The P0 remote-exposure and response-disclosure boundaries plus the P1 diagnostics privacy and browser-security contracts are now remediated. The release remains limited to controlled localhost use until the other P1 reliability, access-control, and workflow findings below are resolved.

The largest product gaps are not cosmetic. Running TTS cancellation is delayed until inference returns, Generate can enqueue duplicates after the POST completes, Local files creates a voice immediately behind an ambiguous action, and Transcribe promises timestamps that the API does not provide.

## Severity model

| Priority | Meaning |
| --- | --- |
| P0 | Release blocker; remote exposure, secret/data disclosure, or destructive behavior with a realistic path |
| P1 | Major production reliability, privacy, or core-workflow defect |
| P2 | Important product completeness, accessibility, or operational quality issue |

## Findings

### VS-QA-001 - P0 - Docker is remotely reachable with authentication disabled by default

**Remediation status: RESOLVED**

**Evidence**

- `docker/Dockerfile:59` binds Uvicorn to `0.0.0.0`.
- `docker/docker-compose.yml:9-10` publishes the container port without a loopback host address.
- `docker/docker-compose.yml:19` defaults `VASSIL_AUTH_REQUIRED` to `false`.
- `.env.example:14` and both example JSON configs also default local authentication to disabled.
- The production-only configuration guard is not activated because Compose defaults `VASSIL_ENV` to `docker`, not `production`.

**Impact**

On Docker Desktop or a LAN host, another machine may be able to list/download voices and jobs, submit inference, inspect diagnostics, and invoke deletion endpoints without credentials.

**Required change**

Bind the published port to `127.0.0.1` by default. Add a separate, explicit LAN profile that requires auth and a strong session secret. Fail startup whenever a non-loopback deployment has neither owner auth nor API-key auth.

### VS-QA-002 - P0 - API responses disclose absolute host paths and subprocess details

**Remediation status: RESOLVED**

**Evidence**

- Posting `CHANGELOG.md` as ASR audio returned HTTP 400 with the complete FFmpeg command and `C:\Users\Administrator\Desktop\VassilStudio\.venv\...\ffmpeg...exe`.
- `backend/vvoice/shared/audio/io.py:89` includes the raw subprocess exception in `AudioError`.
- `backend/vvoice/main.py:154` serializes `str(exc)` directly into the response.
- `backend/vvoice/domains/voices/schemas.py:12` and `backend/vvoice/domains/voices/router.py:186` expose `audio_path` even though `reference_audio_url` already exists.
- The frontend contract repeats the field at `frontend/studio-react/src/lib/api.ts:129`.

**Impact**

Responses disclose the Windows username, repository layout, virtual environment, executable location, and storage layout. This materially increases risk when combined with VS-QA-001.

**Required change**

Return stable user-facing audio errors and log technical exceptions only with `request_id`. Remove `audio_path` from the public voice schema. Validate extension, declared MIME type, and decoded media signature before invoking FFmpeg.

### VS-QA-003 - P1 - The “redacted” support bundle is not safe to share as claimed

**Remediation status: RESOLVED**

**Evidence**

- `backend/vvoice/app/system/router.py:123-128` includes Python and platform metadata.
- `backend/vvoice/app/system/router.py:245-267` includes absolute paths, file counts, capacity, and free disk space.
- `backend/vvoice/app/system/router.py:134-136` calls the archive redacted.
- Public copy says it is “designed for safe sharing” at `frontend/studio-react/src/features/product/ProductShell.tsx:170-182`.
- The authenticated Account and Storage tabs display the full auth database, repo, data, jobs, output, and log paths.

**Impact**

An operator can unintentionally share a Windows username, local directory structure, platform fingerprint, and disk metadata with a support ticket.

**Required change**

Use logical aliases such as `DATA_ROOT/voices`, redact home/workspace prefixes, bucket disk values, and make host metadata an explicit opt-in. Change the UI copy until the archive meets that contract.

### VS-QA-004 - P1 - Browser API keys are persisted in `localStorage` without browser hardening

**Remediation status: RESOLVED**

**Evidence**

- `frontend/studio-react/src/lib/api.ts:2-35` reads, migrates, and writes the API key in `localStorage`.
- Settings exposes copy/show controls and the internal environment name `VASSIL_API_KEYS`.
- HTTP responses only carried `X-Request-ID`; no CSP, `X-Content-Type-Options`, `Referrer-Policy`, or frame policy was present.

**Impact**

Any same-origin script execution can read the long-lived automation key. A shared browser profile also retains it after sign-out.

**Required change**

Prefer owner sessions for the UI. If browser API-key entry remains, keep it in memory by default, offer session-only persistence, never provide one-click copy after save, and add a restrictive CSP plus standard security headers.

**Resolution evidence**

- `frontend/studio-react/src/lib/api.ts` keeps keys in memory or tab-scoped `sessionStorage`, removes
  retired local entries, omits the key for auth routes and active owner sessions, and clears it on
  logout.
- Settings no longer reloads the secret into the form or exposes a copy action after activation.
- `backend/vvoice/shared/security/headers.py` applies the browser header policy; Studio HTML and the
  React entry point coordinate a fresh cryptographic style nonce for each response.
- `backend/vvoice/core/observability.py` and supported launchers disable Uvicorn's query-bearing
  access log while retaining structured, query-free request events.
- The legacy fallback serves its pinned Lucide runtime from the application origin; browser QA
  confirmed 43 icons with no external request or CSP error.
- Static regression tests and Playwright cover memory loss on reload, tab persistence, owner-session
  precedence, legacy-key cleanup, DOM non-disclosure, and logout cleanup.

### VS-QA-005 - P1 - Cancelling a running TTS job does not interrupt inference

**Status: mitigated by an explicit safe-point contract; process-level interruption remains open**

**Evidence**

- A real CPU job reached `running`; cancel returned `cancelling`, but terminal `cancelled` arrived **47.72 seconds** later.
- `backend/vvoice/domains/tts/jobs.py:235-251` checks cancellation before and after `self._tts.synthesize(...)`, not during it.
- The same architectural limitation applies to a long blocking inference call in a worker thread.

**Impact**

The UI says Cancel, but CPU and queue capacity remain occupied. Repeated long requests can make the product appear frozen and prevent urgent work from starting.

**Required change**

Run inference in a killable worker process or add cooperative checkpoints supported by the runtime. Until interruption is real, label the state “Stop requested; current inference is finishing” and expose elapsed time.

**Resolution evidence**

- Job responses now expose `cancellation_mode: safe_point`, `progress_stage`, and `stage_started_at`.
- Generate, Transcribe, Jobs rows, and Job Inspector use `Stopping` plus the actual current stage; they
  no longer imply immediate interruption.
- Success and cancellation transitions are serialized under the job lock. A stop request cannot be
  overwritten by stale worker state, and cancelled TTS work cannot promote a final WAV output.
- Inference still occupies CPU until the current blocking model call returns. A killable worker process
  remains a later runtime architecture option, not a hidden product promise.

### VS-QA-006 - P1 - Generate can enqueue accidental duplicates and leaves stale success copy

**Status: resolved 2026-08-24**

**Evidence**

- A real render produced 2.85 seconds of audio and became visible after about 14.3 seconds.
- Once the create request returned, Generate became enabled while the job was still running.
- `frontend/studio-react/src/features/generate/GenerateView.tsx:151` blocks only while `generateMutation.isPending`, not while an equivalent job is active.
- `frontend/studio-react/src/features/generate/GenerateView.tsx:634-637` continues to show “Job queued” after the job succeeds.

**Impact**

Users can create duplicate expensive jobs and cannot trust the local status message.

**Required change**

Disable or change the primary action while the same voice/script/parameters are active. Add an idempotency key or request fingerprint, derive the message from the server job lifecycle, and expose queue position, elapsed time, progress when available, and cancellation.

**Resolution evidence**

- ASR/TTS create endpoints accept `Idempotency-Key`; same-payload replay returns one job and key reuse
  for a different payload returns `409`. Raw keys are not persisted or returned.
- Generate and Transcribe use synchronous submit locks, retry-stable keys, and persisted job stages.
  Generate remains disabled while an equivalent voice/text/language/steps/speed job is active.
- Playwright invoked each primary action twice in the same browser task and observed exactly one POST
  for TTS and one for ASR at `1440x1000` and `390x844`, with no overflow or browser errors.

### VS-QA-007 - P1 - Local voice import has an ambiguous immediate side effect and permits duplicates

**Evidence**

- Clicking “Prepare profile” created a second profile immediately and selected it for Generate.
- `frontend/studio-react/src/features/voices/VoicesView.tsx:469-486` submits the candidate with its derived name directly.
- The action label is defined at `frontend/studio-react/src/features/voices/VoicesView.tsx:877-883`.
- `backend/vvoice/domains/voices/service.py:35-69` always allocates a UUID and does not check duplicate name or source fingerprint.

**Impact**

The action sounds reversible but writes product data. Repeated clicks create indistinguishable voices, making selection and cleanup error-prone.

**Required change**

Add a review step with editable name, language, transcript, audio preview, duration/quality checks, and a clear “Import voice profile” command. Warn on duplicate name and matching audio fingerprint.

### VS-QA-008 - P1 - Public operational surfaces reveal implementation details

**Evidence**

- With owner auth enabled and no session, `/docs`, `/openapi.json`, `/readyz`, and `/operations` returned HTTP 200.
- `/readyz` lists exact ASR/TTS encoder, decoder, joiner, tokenizer, lexicon, vocoder, and storage check names at `backend/vvoice/app/system/router.py:52-65`.
- FastAPI docs remain enabled by default at `backend/vvoice/main.py:57`.
- Public Support, Operations, and Changelog copy exposes route names, repository files, smoke scripts, OpenAPI regeneration, and commit/push process at `frontend/studio-react/src/features/product/ProductShell.tsx:168-221`.

**Impact**

The public product surface reads like an engineering runbook and exposes an unnecessary system inventory.

**Required change**

Return aggregate readiness publicly and keep detailed checks behind owner auth. Disable or protect OpenAPI docs outside development. Replace public pages with user support, privacy, release notes, and troubleshooting that do not require repository knowledge.

### VS-QA-009 - P1 - Transcribe promises timestamps but only returns plain text

**Evidence**

- The empty state says uploads will show timestamps at `frontend/studio-react/src/features/transcribe/TranscribeView.tsx:423`.
- `backend/vvoice/domains/asr/schemas.py` exposes one `text` string with no segment or word timing fields.
- A real 5.93-second TTS-to-ASR round trip completed in about 0.13 seconds and displayed a correct transcript, but there were no timings, synchronized review, editing, or SRT/VTT export.

**Impact**

The feature does not meet its own promise and is incomplete for a voice-studio transcription workflow.

**Required change**

Either remove the timestamp claim for the small release or add timed segments, completed-audio playback beside the transcript, editing, and TXT/SRT/VTT export.

### VS-QA-010 - P2 - Studio semantics and password labeling are not accessibility-ready

**Evidence**

- Generate, Voices, Transcribe, Realtime, Jobs, and Settings have no page-level `h1`; the route title is a `span` at `frontend/studio-react/src/components/app-shell/AppShell.tsx:116-122`.
- The password control wraps both the input and show/hide button in one label at `frontend/studio-react/src/features/auth/AuthPage.tsx:239-265`.
- Browser role lookup for “Password” matched both elements, and the textbox accessible name became “Password Show password”.

**Impact**

Screen-reader users do not get reliable page navigation, and the password field has a noisy/ambiguous accessible name.

**Required change**

Render one visible or visually hidden `h1` per route. Use `label htmlFor` with an input `id`, keep the toggle outside the label relationship, and add an automated Axe pass to browser QA.

### VS-QA-011 - P2 - Authentication loses deep links and logout does not clear user drafts

**Evidence**

- Opening `/studio#/settings` while signed out redirected to `/login#/settings`; successful login then navigated to `/studio`, losing Settings.
- `frontend/studio-react/src/features/auth/AuthPage.tsx:31-35` always assigns `/studio` after login.
- The Generate draft remained visible after sign-out and sign-in because `frontend/studio-react/src/lib/studio-preferences.ts:78-93` persists the script in `localStorage`.

**Impact**

Users lose intended navigation and may be surprised that script content survives logout on a shared browser.

**Required change**

Use a validated same-origin `return_to` route. Scope preferences by account and document autosave; offer clear-on-logout or a “Clear local drafts” control.

### VS-QA-012 - P2 - Quality gate is healthy but not portable or fully representative

**Evidence**

- A direct `scripts/check.ps1` run failed at frontend lint because the machine PATH contains a malformed quoted entry before Node.
- Prepending `C:\Program Files\nodejs` allowed the full gate to pass.
- The four Playwright scripts pass, but they are not called by `scripts/check.ps1` and rely heavily on mocked API/runtime fixtures.

**Impact**

The documented one-command gate can fail on a valid Node installation, while a passing gate still does not cover the real authenticated browser/runtime path.

**Required change**

Resolve `node.exe`, prepend its parent for npm child processes, and emit an actionable PATH diagnostic. Add a fast authenticated browser smoke to the normal gate and keep real model/browser E2E as an explicit release task.

### VS-QA-013 - P1 - Completed audio is hidden in Jobs and direct media bypasses API-key auth

**Status: RESOLVED on 2026-08-24.**

The queue row exposed only an unlabeled details icon, while playback was nested inside the inspector.
The inspector used a direct media URL, which works for anonymous or cookie sessions but cannot attach
the API-key header required by temporary automation access.

**Resolution**

- Every job with retained audio now exposes a visible `Listen` action directly in the queue.
- The inline and inspector players fetch through the authenticated API client, use a revocable
  `blob:` URL, and provide loading, error, retry, playback, and deterministic WAV download states.
- Playwright exercises playback and download at desktop/mobile sizes and asserts that media requests
  carry the API-key header without putting the key in the URL.
- The repository quality gate passes with `148` pytest cases plus frontend lint/typecheck/build,
  OpenAPI export, auth/product smoke, and Docker Compose validation.

## Workflow completeness

| Workflow | What works | Missing for a small complete product |
| --- | --- | --- |
| Landing | Responsive, local assets, clear primary CTA, no broken content images | Add a real favicon; replace engineering language with user outcomes; localize VI/EN; make privacy claims conditional and precise |
| Setup/Auth | First-owner setup, invalid-login error, protected Studio/API routes, logout, password change/rate-limit tests | Preserve deep link; recovery/reset procedure; clear local-data policy; secure non-loopback defaults |
| Generate | Voice/language/speed/mode selection, idempotent queue, active-state lock, progress, output player/download, history handoff | Output filename/format, batch takes, pronunciation controls, benchmark-backed ETA |
| Voices | Upload/local import, metadata edit, audio preview, search/filter, delete | Review-before-import, duplicate detection, trim/silence/clipping checks, replace source audio, tags/backup/export |
| Transcribe | File staging/preview, VI/EN selection, queue, result copy/download, Generate handoff | Timed segments, editing, completed-source playback in context, SRT/VTT, multi-file batch |
| Realtime | Real WebSocket smoke, mocked browser capture, language selection, segments, copy/download, stop/finalize | Microphone selector, pause/resume, reconnect behavior, saved session history, live permission/device diagnostics |
| Jobs | Search/filter, status summaries, inline authenticated playback/download, inspector, retry/reuse, cleanup/delete confirmation | Titles/favorites, take comparison, server pagination/sort, batch actions, real progress, prompt cancellation, retention policy visibility |
| Settings | Readiness, warmup, storage inventory, auth/account, cleanup, diagnostics | Safe paths, model install/update/unload, editable runtime controls, log viewer, backup/restore, open-data-folder action |

## Verification results

### Passed

- `109 passed` with pytest.
- Ruff passed.
- Frontend lint, TypeScript build, and Vite production build passed.
- OpenAPI export passed.
- Auth/product smoke passed.
- Docker Compose configuration validation passed.
- API, Voices, TTS, TTS job, ASR, ASR job, and realtime WebSocket smokes passed.
- Playwright QA passed: Landing (desktop/tablet/mobile), Audio workflows (desktop/mobile), Jobs (desktop/mobile), Settings (desktop/mobile).
- Manual browser pass showed no console errors and no page-level horizontal overflow at 1920, 768, and 390 px.
- Path traversal filename probe did not write outside the job directory; `safe_display_filename` normalized the display name.

### Failed or qualified

- Direct `scripts/check.ps1` failed until Node's directory was prepended to PATH.
- Invalid audio returns an over-detailed 400 response instead of a stable sanitized media error.
- Browser requests to `/favicon.ico` returned 404; no favicon declaration exists in the frontend.
- TTS running cancellation took 47.72 seconds to reach terminal state.
- Real TTS UI latency was about 14.3 seconds for 2.85 seconds of output on the audited CPU configuration.
- English end-to-end quality was not scored because the workspace has no English voice profile.
- Physical microphone permission/capture was not granted during browser control; browser capture was exercised with the existing Playwright fixture and the real WebSocket protocol passed separately.
- Docker runtime smoke, GPU execution, multi-client load, long soak, and adversarial file fuzzing were outside this pass.

## Recommended implementation order

1. **Security boundary:** protect detailed docs/readiness; loopback defaults, response sanitization, diagnostics path filtering, and browser response security are resolved.
2. **Runtime control:** safe-point cancellation semantics, idempotency, duplicate-submit locks, and server-derived stages are resolved; process-level inference interruption remains optional future work.
3. **Voice/ASR product closure:** add voice import review/quality checks and either implement timed transcripts or remove the timestamp promise.
4. **Account/privacy:** preserve deep links and scope/clear local drafts; browser API-key persistence is removed and diagnostics sharing is now explicit.
5. **Product completeness:** VI/EN UI localization, output naming/formats, realtime device selection, model management, backup/restore, and log workflow.
6. **QA gate:** portable Node invocation, Axe checks, authenticated real-browser smoke, and a later opt-in Docker/language matrix release pass.
