# Changelog

All notable VassilStudio productionization changes are tracked here.

## 0.1.0-local-product - 2026-07-08

### Added

- Product shell at `/` with public trust/support/license/changelog routes.
- Local owner setup, login, logout, HttpOnly session cookies, and protected Studio routing.
- Local owner password change from Settings with other-session revocation.
- API key compatibility for automation when Studio auth is required.
- Settings account/session surface, open-source license metadata, diagnostics metadata, and privacy-filtered diagnostics bundle.
- First output onboarding checklist in Generate.
- Storage usage and terminal job retention controls in Settings.
- Auth/product smoke in `scripts/check.ps1`.
- Latency benchmark scripts for TTS, ASR, and realtime chunking.
- Operations guide with install, model layout, auth, smoke, Docker, backup, and troubleshooting.
- Product-grade trust pages for privacy, support, license, changelog, and operations.
- Release metadata aligned across backend, health/diagnostics, OpenAPI, and React package files.
- Native `run_api.ps1` loads `.env`, and `.env.example` points to an existing default config.
- Explicit local/development/production/docker runtime profiles and effective log-level diagnostics.
- A pinned, read-only Windows GitHub Actions quality gate with clean npm installs and OpenAPI drift checks.
- Explicit `httpx2` test-client coverage so clean CI and local test environments use the same Starlette path.
- Exact pytest and Ruff versions for deterministic local and GitHub quality-gate behavior.
- Hermetic config and ZipVoice frontend tests that do not inherit host settings or require local model files.
- Patched frontend transitive advisories and a blocking high-severity npm audit in CI mode.
- Split lightweight unit-test dependencies from model runtime engines for faster clean CI installs.
- Pinned a matching Torch/Torchaudio pair and forced CPU-only wheels in the Docker runtime image.
- Digest-pinned Docker bases and a reviewed Linux/Python 3.12 CPU constraints set.
- Audited source release builder with version/tag checks, private-file rejection, manifest, and SHA256 sums.
- GPL-3.0-or-later application license, principal third-party notices, and explicit model-license boundary.
- Reproducible benchmark protocol, RC Windows CPU baseline, and model fingerprints.
- Generate workspace with persistent drafts, script metadata, reference-audio preview, and real queue/output state.
- Voice library with direct audio upload, local candidate mode, language filters, selected-profile state, and inline validation.
- Transcription workspace with staged audio validation, explicit queueing, recent results, and transcript handoff to Generate.
- Realtime workspace with session readiness, chronological combined output, bounded segment rendering, and transcript export.
- Priority-ordered job history with responsive filters, conditional actions, and incremental history rendering.
- Settings workspace split into focused runtime, account, storage, and security views with real operational states.
- First-run and login flows with password confirmation, visibility controls, API retry, and guarded submission.
- Public product shell with an actual Studio workspace image, complete workflow overview, and local-runtime trust signals.
- Privacy, license, support, changelog, and operations pages with shared navigation and documentation-style sections.
- Proof-led landing experience with a crisp product hero and interactive Generate, Transcribe, Realtime, and Voices previews.
- Repeatable Playwright landing QA for desktop, tablet, and mobile layout, image, overflow, and browser-error checks.
- Brand-specific acoustic sculpture hero with first-viewport product proof and documented generation provenance.
- Jobs history now exposes inline authenticated playback, stable WAV downloads, and shared
  loading/error/retry media states in both queue rows and the job inspector.
- Evidence-backed product completeness research defines the local-first scope and prioritizes
  runtime integrity, transcript review/export, voice intake, realtime sessions, and model operations.
- Idempotent ASR/TTS job creation with request fingerprints, replay-safe retries, explicit progress
  stages, and safe-point cancellation capability in the public contract.

### Hardened

- Studio browser access now prefers the HttpOnly owner session. Temporary automation keys stay in
  memory by default, may opt into tab-scoped `sessionStorage`, are never copied back into the form,
  and are cleared on logout; retired `localStorage` entries are removed automatically.
- Browser responses now include a restrictive Content Security Policy, a cryptographic per-response
  nonce for Radix runtime styles, clickjacking/MIME/referrer/permissions protections, auth no-store
  caching, same-origin-only WebSockets, and HTTPS-only HSTS. Nonced HTML is never cached.
- ASR/TTS metadata reads now share the job-state lock with atomic writes, preventing transient
  Windows polling failures while a worker replaces `metadata.json`.
- Uvicorn access logging is disabled in application logging, native launch, and Docker launch paths;
  the structured HTTP logger records paths without query strings so WebSocket keys are not persisted.
- The tracked fallback Studio now loads a pinned same-origin Lucide runtime instead of executable
  JavaScript from a public CDN.
- Diagnostics now expose logical storage aliases and bucketed inventory/disk values; support bundles
  exclude host fingerprints by default and require an explicit per-download opt-in to include them.
- Docker Compose and native launchers bind to loopback by default; direct images fail closed, and
  anonymous non-loopback startup plus remote first-owner setup are rejected.
- Audio uploads now require a supported extension, declared media type, and matching container
  signature before decoding.
- Public HTTP, queued-job, realtime, and Voice contracts redact decoder commands, model paths,
  legacy raw job failures, and local voice storage paths.
- Split ASR/TTS CPU thread tuning, measured 4/8-step render profiles, and active queue polling reduce local render wait without weakening the quality smoke gate.
- Request IDs, structured HTTP/job logs, liveness/readiness split, request upload limits, and path-safe Studio static serving.
- Local auth login and password change attempts are rate-limited with `429` and `Retry-After`.
- New local account passwords use scrypt hashes while legacy PBKDF2 hashes remain verifiable.
- ASR/TTS job lifecycle with cancellation, retry metadata, cleanup, and consistent terminal states.
- Job terminal transitions are lock-protected; cancelled TTS work cannot be overwritten by a stale
  success transition, and output WAV files are atomically promoted only after the final stop check.
- Generate, Transcribe, and Jobs Run again guard synchronous double submits, preserve idempotency keys
  across request retries, and render progress/cancellation copy from server lifecycle state.
- Language-aware ASR/TTS runtime selection and model readiness reporting.
- Realtime session shutdown now waits for the backend final transcript before closing the websocket, with a bounded timeout fallback.
- Studio navigation keeps runtime status actionable on small screens and handles drawer/session failures explicitly.
- Auth-enabled startup now requires a strong non-placeholder session secret; production profile
  startup also requires auth, secure cookies, and debug mode off.
- ZipVoice text processing uses the index-resolvable `phonemizer-fork` and `espeakng-loader` path,
  removing the clean-install dependency on a separately built `piper_phonemize` wheel.
- Doctor rejects model runtime version drift, including mismatched Torch and TorchAudio builds.

### Verified

- Runtime Integrity P1-A passed `153` backend tests, the full `scripts/check.ps1` gate, and desktop/mobile
  Playwright coverage proving one POST per double submit, idempotency headers, lifecycle stages,
  authenticated recovery, and zero horizontal overflow.
- Jobs playback passed authenticated media-header, blob-source, failure/retry, auto-play,
  WAV-download, inspector, recovery-action, and responsive Playwright checks at desktop and mobile
  viewports; the repository gate passed with `148` backend tests.

- Browser Security P1 passed `147` backend tests, frontend lint/build, Settings Playwright credential
  regression QA at desktop and mobile viewports, and live CSP/security-header probes.
- Diagnostics Privacy P1 passed `143` backend tests, frontend lint/build, OpenAPI/auth/Compose gates,
  live default/opt-in archive scans, and Settings Playwright QA at desktop and mobile viewports.
- Security Boundary P0 passed `142` backend tests, frontend lint/build, OpenAPI/auth/Compose gates,
  live disclosure probes, and a clean Docker build/runtime smoke on loopback.
- `scripts/check.ps1` passes with ruff, pytest, React lint/build, OpenAPI export, auth/product smoke, and Docker Compose config validation.
- Native sample-voice E2E, VI/EN language matrix, Docker infrastructure smoke, and Docker sample-voice E2E pass on the RC workstation.
- The CPU-only Docker image is about 83 percent smaller than the accidental CUDA-bearing image it replaces.
