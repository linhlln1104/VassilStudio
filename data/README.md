# VassilStudio Runtime Data

Runtime data is local and intentionally not committed.

Recommended layout:

```text
data/
  voices/
  jobs/
    asr/
    tts/
  uploads/
  outputs/
  production/
    production.sqlite3
    references/
    audio/
    exports/
  model-deployments.sqlite3
  worker-control.sqlite3
  auth.sqlite3
```

`data/voices` stores reusable reference voices, including loose import candidates such as
`sample voice.weba`. Saved profiles carry a `language` field (`vi` or `en`) so Studio and the API
route ASR/TTS work to the matching local model.

`data/jobs` stores async ASR/TTS job metadata and generated job artifacts. Smoke scripts may create
and clean temporary jobs while leaving downloaded verification audio under `tmp/smoke`.

Saved voice profile metadata stores reference audio paths relative to each voice directory. This
keeps profiles portable between local runs and Docker mounts. Older metadata with absolute audio
paths is still read for compatibility.

Docker mounts `./data` into `/app/data` as writable storage.

Each job domain also contains a SQLite WAL dispatch queue/index and OS lock files.
Production audio belongs to its retained take and survives ordinary job cleanup.
Auth stores hashed keys, scoped accounts, sessions and audit events. Back up all data
together after stopping API and worker, or use coordinated SQLite-aware live snapshots.
Never copy only the main SQLite files while WAL writers run. See `docs/worker.md` and
`docs/production-workflows.md` for recovery, versioning and export behavior.
