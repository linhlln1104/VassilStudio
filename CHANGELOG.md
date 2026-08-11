# Changelog

All notable VassilStudio productionization changes are tracked here.

## 0.1.0-local-product - 2026-07-08

### Added

- Product shell at `/` with public trust/support/license/changelog routes.
- Local owner setup, login, logout, HttpOnly session cookies, and protected Studio routing.
- Local owner password change from Settings with other-session revocation.
- API key compatibility for automation when Studio auth is required.
- Settings account/session surface, open-source license metadata, diagnostics metadata, and redacted diagnostics bundle.
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

### Hardened

- Request IDs, structured HTTP/job logs, liveness/readiness split, request upload limits, and path-safe Studio static serving.
- Local auth login and password change attempts are rate-limited with `429` and `Retry-After`.
- New local account passwords use scrypt hashes while legacy PBKDF2 hashes remain verifiable.
- ASR/TTS job lifecycle with cancellation, retry metadata, cleanup, and consistent terminal states.
- Language-aware ASR/TTS runtime selection and model readiness reporting.
- Realtime session shutdown now waits for the backend final transcript before closing the websocket, with a bounded timeout fallback.
- Auth-enabled startup now requires a strong non-placeholder session secret; production profile
  startup also requires auth, secure cookies, and debug mode off.
- ZipVoice text processing uses the index-resolvable `phonemizer-fork` and `espeakng-loader` path,
  removing the clean-install dependency on a separately built `piper_phonemize` wheel.
- Doctor rejects model runtime version drift, including mismatched Torch and TorchAudio builds.

### Verified

- `scripts/check.ps1` passes with ruff, pytest, React lint/build, OpenAPI export, auth/product smoke, and Docker Compose config validation.
- Native sample-voice E2E, VI/EN language matrix, Docker infrastructure smoke, and Docker sample-voice E2E pass on the RC workstation.
- The CPU-only Docker image is about 83 percent smaller than the accidental CUDA-bearing image it replaces.
