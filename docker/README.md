# VassilStudio Docker

Docker assets live here so the repository root stays focused on source layout.
See `../docs/operations.md` for the full local operations runbook.

The Docker image builds `frontend/studio-react` in a Node stage and serves the public product shell
from `/` plus the Studio app from `/studio` through the FastAPI app.

Run from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_docker.ps1
```

Or directly:

```powershell
docker compose -f .\docker\docker-compose.yml up --build
```

Run a disposable Docker smoke check on port `8018`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_docker.ps1
```

Docker Desktop or the Docker service must be running before this smoke check can start containers.
Use `-KeepRunning` if you want to inspect the container after the smoke check.

The compose service mounts:

- `../models` -> `/app/models` read-only
- `../config` -> `/app/config` read-only
- `../data` -> `/app/data` writable
- `../logs` -> `/app/logs` writable

Copy `.env.example` to `.env` if you want local defaults for compose variables.

To require browser login in Docker, set these values in `.env` before starting compose:

```powershell
VASSIL_AUTH_REQUIRED=true
VASSIL_SESSION_SECRET=<random value with at least 32 characters>
```

Compose uses the `docker` runtime profile by default. For an HTTPS deployment, set
`VASSIL_ENV=production` and `VASSIL_SECURE_COOKIES=true`; the app validates these production
invariants before startup.

The local account/session database is stored under the writable `../data` volume.

The Dockerfile is the supported production-like local build recipe for VassilStudio 0.1.x. A
prebuilt image is not an official release artifact yet. Models remain external read-only assets,
and binary redistribution must satisfy the notice, corresponding-source, SBOM, signing, and
clean-host smoke requirements in `../docs/releasing.md`.

The image uses digest-pinned base image indexes and
`runtime-linux-cpu.constraints.txt` for its Python 3.12 CPU package set. Treat an update to either
as a runtime release change that requires Docker E2E and a new accepted benchmark baseline.
