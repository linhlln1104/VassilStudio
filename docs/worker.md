# Run inference in a separate process

The default `VASSIL_WORKER_MODE=embedded` runs durable inference workers inside the
API process. Use `external` for an API process that validates/adopts jobs while a
separate process owns model loading and inference. Both processes must use the same
configuration and local data directory. This mode supports one inference worker
host and one API on the same machine; it is not a network worker protocol.

In PowerShell, start the API from the repository directory:

```powershell
$env:VASSIL_WORKER_MODE = "external"
$env:VASSIL_CONFIG = (Resolve-Path .\config\vassil.local.json).Path
.\.venv\Scripts\python.exe -m uvicorn vvoice.main:create_app --factory --host 127.0.0.1 --port 8000
```

In a second terminal, start the worker using the same configuration:

```powershell
.\.venv\Scripts\python.exe -m vvoice.worker --config .\config\vassil.local.json
```

Use your configured `config/vassil.local.json` (see the model setup guide). The worker CLI
sets embedded execution for its own child process environment; it does not change
the API or machine environment. On Linux, the equivalent executables are
`.venv/bin/python`, with `VASSIL_WORKER_MODE=external VASSIL_CONFIG=/absolute/config.json`
preceding the uvicorn command. Run only one uvicorn worker for this local deployment.

For `.env` loading on Windows, use `scripts/run_api.ps1` and `scripts/run_worker.ps1`
in separate terminals. Both preserve variables already present in the process.
API auto-reload is opt-in (`scripts/run_api.ps1 -Reload`) for development.

Start the worker before submitting synchronous generation/transcription or model
warmup requests. Stop the worker with Ctrl+C. It stops claiming new jobs, finishes
already claimed jobs, and releases model resources. Pending queue records survive
either process restarting. Restart the worker with the same command; do not delete
queue databases to recover a process.

## Execution and control

- HTTP `/synthesize` and `/transcribe` use immutable durable jobs and wait for their
  results, with a default 600-second deadline. They do not load models inside the
  API. A timeout requests cancellation using existing job safe-point semantics;
  retained job IDs in logs/metadata permit inspection. Requests fail promptly if no
  fresh worker heartbeat exists.
- Production batches remain scheduled by the API. The worker CLI does not start a
  second production scheduler. Accepted pending batch rows resume when the API
  returns; already accepted TTS/ASR jobs continue without the API.
- Warmup, unload, model enable/disable, import, activation and rollback are explicit
  commands in `data/worker-control.sqlite3`. There are no arbitrary Python calls or
  pickled payloads. Model changes execute in the worker before the API updates its
  local validation metadata.
- Pending commands expire at their request deadline. A started command may finish
  after its client times out; inspect model state before retrying. A command running
  during a worker crash is marked failed on restart and is not silently replayed.
- A separate heartbeat publishes model loaded state and ASR loaded languages. A
  heartbeat older than 10 seconds is offline: stale model residency is never shown
  as loaded. Asset availability and an online worker are separate readiness checks.
- The CLI acquires `data/.worker-host.lock` before constructing either queue. Queue
  workers also use OS ownership locks, and shared inference admission serializes
  native execution across processes. Locks are released by the OS after a crash.
  Lock files may remain on disk; their existence alone does not mean a live owner.

## Operations

Do not run an embedded API and the external worker against the same queue. Stop the
API before changing its worker mode. The external worker uses the API environment
for ZipVoice/ASR and the configured `.venv-vieneu` subprocess for VieNeu; separate
worker mode does not remove the optional runtime installation requirements.

Use local storage for the SQLite WAL databases and OS locks. Do not place this data
directory on an untested network share. Back up the whole data directory with an
SQLite-aware snapshot, or stop both processes first. Include production assets,
model deployment metadata, both job queues and the control database. Model weights
may be restored separately using the pinned setup manifests.

This separation contains worker process failure and permits independent API
restarts. Cancellation remains safe-point based for native model calls; it is not
an immediate hard-kill SLA for every engine. Long-running model operations may delay
graceful worker shutdown. VieNeu retains its own bounded subprocess timeout.
