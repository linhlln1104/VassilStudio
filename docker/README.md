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
VASSIL_SESSION_SECRET=replace-with-random-32-plus-character-secret
```

The local account/session database is stored under the writable `../data` volume.
