# VassilStudio Docker

Docker assets live here so the repository root stays focused on source layout.

The Docker image builds `frontend/studio-react` in a Node stage and serves the generated assets
from `/studio` through the FastAPI app.

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
