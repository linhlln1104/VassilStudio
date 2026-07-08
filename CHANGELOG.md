# Changelog

All notable VassilStudio productionization changes are tracked here.

## 0.1.0-local-product - 2026-07-08

### Added

- Product shell at `/` with public trust/support/license/changelog routes.
- Local owner setup, login, logout, HttpOnly session cookies, and protected Studio routing.
- Local owner password change from Settings with other-session revocation.
- API key compatibility for automation when Studio auth is required.
- Settings account/session surface, local license placeholder, diagnostics metadata, and redacted diagnostics bundle.
- First output onboarding checklist in Generate.
- Storage usage and terminal job retention controls in Settings.
- Auth/product smoke in `scripts/check.ps1`.
- Latency benchmark scripts for TTS, ASR, and realtime chunking.
- Operations guide with install, model layout, auth, smoke, Docker, backup, and troubleshooting.
- Product-grade trust pages for privacy, support, license, changelog, and operations.
- Release metadata aligned across backend, health/diagnostics, OpenAPI, and React package files.

### Hardened

- Request IDs, structured HTTP/job logs, liveness/readiness split, request upload limits, and path-safe Studio static serving.
- Local auth login and password change attempts are rate-limited with `429` and `Retry-After`.
- ASR/TTS job lifecycle with cancellation, retry metadata, cleanup, and consistent terminal states.
- Language-aware ASR/TTS runtime selection and model readiness reporting.

### Verified

- `scripts/check.ps1` passes with ruff, pytest, React lint/build, OpenAPI export, auth/product smoke, and Docker Compose config validation.
