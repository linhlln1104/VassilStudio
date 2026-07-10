# VassilStudio Operations Guide

This guide is the production runbook for a small local-first VassilStudio install. It covers native
Windows/local runs, Docker, model layout, auth, smoke checks, diagnostics, backup, and common
failure modes.

## Supported Runtime Modes

| Mode | Use when | Entry point |
| --- | --- | --- |
| Native local | Developing or running on a workstation with local models | `scripts/run_api.ps1` |
| Production-like local | Same machine, browser login required, API key for automation | `.env` + `VASSIL_AUTH_REQUIRED=true` |
| Docker | Packaging validation or repeatable runtime with mounted volumes | `scripts/run_docker.ps1` |

VassilStudio is local-first. Model files, voice profiles, transcripts, generated audio, jobs, logs,
and account/session data stay in the local workspace unless an operator copies them elsewhere.

## Native Quick Start

Run these commands from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_storage.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_api.ps1
```

Open <http://127.0.0.1:8000/> for the product shell or <http://127.0.0.1:8000/studio> for the
Studio workspace.

For production-like local use, copy `.env.example` to `.env` and set at least:

```powershell
VASSIL_AUTH_REQUIRED=true
VASSIL_SESSION_SECRET=<random value with at least 32 characters>
```

Generate a secret without storing it in shell history, then place the output in `.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

The app refuses to start when auth is enabled with a missing, short, or documented placeholder
secret. Keep `VASSIL_ENV=local` for a loopback HTTP install. Set `VASSIL_ENV=production` only behind
HTTPS; the production profile requires auth, `VASSIL_SECURE_COOKIES=true`, and debug mode off.

On first visit, `/studio` redirects to `/setup` and creates the local owner account.
`scripts/run_api.ps1` loads `.env` automatically for native local runs. Existing process
environment variables still take precedence.

## Workspace Layout

| Path | Purpose | Backup |
| --- | --- | --- |
| `config/` | Runtime config templates and local config files | Yes, without secrets |
| `models/runtime/` | ASR/TTS model files loaded by the app | Yes or reinstall from source |
| `models/source/` | Original checkpoints, exports, traceability assets | Optional |
| `data/voices/` | Voice profiles and reference clips | Yes |
| `data/jobs/asr/` | ASR job metadata and uploaded audio copies | Optional, depends on retention |
| `data/jobs/tts/` | TTS job metadata and output references | Optional, depends on retention |
| `data/uploads/` | Uploaded files used by workflows | Optional |
| `data/outputs/` | Generated/exported audio | Yes if outputs matter |
| `data/auth.sqlite3` | Local owner account and session store | Yes, protect as sensitive |
| `logs/` | Structured local logs | Optional, useful for support |
| `tmp/` | Smoke and benchmark outputs | No |

Do not commit `data/`, `logs/`, `tmp/`, `.env`, or local model binaries.

## Model Layout

Default config expects these runtime files:

| Language | Workflow | Required files |
| --- | --- | --- |
| `vi` | ASR ZipFormer | `models/runtime/asr/vi/zipformer/encoder.onnx`, `decoder.onnx`, `joiner.onnx`, `tokens.txt` |
| `en` | ASR ZipFormer | `models/runtime/asr/en/zipformer/encoder.onnx`, `decoder.onnx`, `joiner.onnx`, `tokens.txt` |
| `vi` | TTS ZipVoice | `models/runtime/tts/vi/zipvoice/text_model.onnx`, `flow_matching_model.onnx`, `vocos_24khz.onnx`, `tokens.txt`, `lexicon_vi_minimal.txt`, `espeak-ng-data/` |
| `en` | TTS ZipVoice | `models/runtime/tts/en/zipvoice/text_model.onnx`, `flow_matching_model.onnx`, `vocos_24khz.onnx`, `tokens.txt`, `espeak-ng-data/` |

Validate model readiness with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor.ps1
Invoke-WebRequest http://127.0.0.1:8000/model-status
```

Use Studio Settings -> Warm models or call:

```powershell
Invoke-WebRequest -Method POST http://127.0.0.1:8000/warmup
```

## Config And Secrets

Config comes from `VASSIL_CONFIG`, environment variables, then defaults. Keep production-like local
values in `.env`, not in tracked JSON.

Important environment variables:

| Variable | Purpose |
| --- | --- |
| `VASSIL_ROOT` | Repository/workspace root |
| `VASSIL_CONFIG` | JSON config path |
| `VASSIL_ENV` | Runtime profile: `local`, `development`, `production`, or `docker` |
| `VASSIL_DEBUG` | Override runtime debug mode |
| `VASSIL_WARMUP_ON_STARTUP` | Warm all configured ASR/TTS models during startup |
| `VASSIL_AUTH_REQUIRED` | Require browser login for Studio and protected APIs |
| `VASSIL_AUTH_DB_PATH` | Local SQLite account/session database path |
| `VASSIL_SESSION_SECRET` | HMAC secret for session token hashes |
| `VASSIL_SECURE_COOKIES` | Use secure cookies behind HTTPS |
| `VASSIL_API_KEYS` | Comma-separated automation keys |
| `VASSIL_LOG_LEVEL` | Local log verbosity |
| `VASSIL_TELEMETRY_ENABLED` | Reserved opt-in flag; keep `false` for MVP |

Never paste real API keys, session secrets, cookies, transcripts, or private audio into issue
reports. Use the diagnostics bundle instead.

## Auth Operations

Studio local auth is disabled by default for developer convenience. When enabled:

- `/studio` redirects to `/setup` until the owner account exists.
- Passwords are stored as one-way hashes in `data/auth.sqlite3`.
- Sessions use HttpOnly cookies and are invalidated on logout.
- Settings can change the owner password and revoke other active sessions.
- Repeated failed login or password change attempts return `429` with `Retry-After`.
- API key auth remains available for scripts and integrations.
- Runtime profile, effective log level, and cookie security are visible in redacted diagnostics.

If the owner password is lost, stop the app, back up `data/auth.sqlite3`, then remove or replace the
auth database and run `/setup` again. This resets local accounts and sessions only; voice profiles and
jobs remain under `data/`.

## Health And Readiness

| Endpoint | Purpose | Auth |
| --- | --- | --- |
| `/livez` | Process liveness | Public |
| `/readyz` | App readiness | Public |
| `/health` | Runtime feature health | Public |
| `/model-status` | Model/runtime readiness detail | Session or API key when auth is required |
| `/diagnostics` | Redacted runtime/security/storage/license metadata | Session or API key when auth is required |
| `/diagnostics/bundle` | Redacted support zip | Session or API key when auth is required |

Download a support bundle:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/diagnostics/bundle -OutFile diagnostics.zip
```

## Quality Gates

Every production change should pass:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

Default check includes storage setup, doctor, OpenAPI export, ruff, React lint/build, legacy frontend
syntax checks, pytest, auth/product smoke, and Docker Compose config validation.

Optional release checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunE2E
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunLanguageMatrix
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -RunDocker
```

## Smoke Scripts

| Script | Requires live API | What it validates |
| --- | --- | --- |
| `scripts/smoke_auth.ps1` | No | Product shell, setup, login, password change, protected Studio, API key automation |
| `scripts/smoke_api.ps1` | Yes | Health, readiness, model status, OpenAPI |
| `scripts/smoke_voices.ps1` | Yes | Voice import/update/delete workflow |
| `scripts/smoke_tts.ps1` | Yes | Direct synthetic TTS output |
| `scripts/smoke_tts_job.ps1` | Yes | Queued TTS job lifecycle |
| `scripts/smoke_asr.ps1` | Yes | Direct ASR transcription |
| `scripts/smoke_asr_job.ps1` | Yes | Queued ASR job lifecycle |
| `scripts/smoke_realtime.ps1` | Yes | WebSocket realtime chunk path |
| `scripts/smoke_language_matrix.ps1` | Yes | VI/EN configured ASR/TTS matrix |
| `scripts/smoke_cleanup_jobs.ps1` | Yes | Terminal job cleanup API |
| `scripts/smoke_docker.ps1` | Docker | Container start, health, model status |

When auth is required, set `VASSIL_API_KEY` for live smoke scripts.

## Benchmarks

Latency benchmarks require a live API and write JSON summaries under `tmp/benchmarks/`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_tts_latency.ps1 --iterations 1 --num-steps 8
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_asr_latency.ps1 --iterations 3
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\benchmark_realtime_chunking.ps1 --chunks 5
```

Use these numbers as local baselines, not universal SLA promises. CPU, model size, threads, warmup,
and audio length materially affect latency.

## Docker Operations

Start Docker runtime from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_docker.ps1
```

Compose mounts:

- `./models` to `/app/models` read-only
- `./config` to `/app/config` read-only
- `./data` to `/app/data` writable
- `./logs` to `/app/logs` writable

Run Docker smoke:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_docker.ps1
```

Docker Desktop or the Docker service must be running before Docker smoke starts containers.

## Storage Cleanup

Use Studio Settings -> Storage and retention to remove terminal ASR/TTS jobs. The cleanup controls
remove succeeded, failed, and cancelled jobs only. Active jobs are kept.

API cleanup examples:

```powershell
Invoke-WebRequest -Method DELETE "http://127.0.0.1:8000/api/v1/tts/jobs?max_age_seconds=604800"
Invoke-WebRequest -Method DELETE "http://127.0.0.1:8000/api/v1/asr/jobs?max_age_seconds=604800"
```

## Backup And Restore

To back up a local workspace, stop the app and copy:

- `config/` local files, excluding secrets if sharing externally
- `models/runtime/` if models are not easily reinstalled
- `data/voices/`
- `data/outputs/`
- `data/auth.sqlite3`
- any job directories that need audit/history retention

To restore, copy the same paths into a fresh checkout, run `scripts/setup_storage.ps1`, then run
`scripts/doctor.ps1` and `scripts/check.ps1`.

## Windows Notes

- Prefer a short path without spaces for native runtime work, for example `C:\VassilStudio`.
- Avoid placing model files in synced or permission-heavy folders when diagnosing ONNX/native DLL
  load errors.
- Use PowerShell scripts with `-ExecutionPolicy Bypass` as shown in this guide.
- If `npm` is blocked by PowerShell execution policy, use `npm.cmd`, matching `scripts/check.ps1`.
- Keep model paths under the workspace unless a config explicitly points elsewhere.

## Troubleshooting

| Symptom | Check | Fix |
| --- | --- | --- |
| `/studio` redirects to `/setup` unexpectedly | `GET /api/v1/auth/status` | Create owner account or verify `VASSIL_AUTH_DB_PATH` points to the intended DB |
| Login works but API smoke returns 401 | API key headers/env | Set `VASSIL_API_KEY` for smoke scripts or add `VASSIL_API_KEYS` to server env |
| Model status is not ready | `scripts/doctor.ps1` | Restore missing model/tokenizer/vocoder files for the requested language |
| TTS fails for a language | TTS language config | Verify ZipVoice tokens, vocoder, eSpeak data, and language selection |
| Upload rejected | file size/type | Check `limits.max_upload_bytes` and use supported audio formats |
| Realtime disconnects | WebSocket URL and API key | Include API key when auth is required and verify `/model-status` first |
| Startup rejects session configuration | `VASSIL_AUTH_REQUIRED`, `VASSIL_SESSION_SECRET`, runtime profile | Generate a random 32+ character secret; for `production`, also enable secure cookies and HTTPS |
| Docker smoke cannot start | Docker daemon | Start Docker Desktop/service, then rerun `scripts/smoke_docker.ps1` |
| Diagnostics bundle is needed | `/diagnostics/bundle` | Attach the zip to support; it is redacted by default |

## Release Checklist

Before tagging or distributing a production-like local build:

- `scripts/check.ps1` passes.
- Optional E2E, language matrix, and Docker smokes pass when models and Docker are available.
- Backend version, React package version, and `CHANGELOG.md` release name are aligned.
- `CHANGELOG.md` has the release notes.
- `contracts/openapi/` is regenerated.
- `.env.example`, Docker docs, and this operations guide match current behavior.
- No secrets or private audio are present in git status.
