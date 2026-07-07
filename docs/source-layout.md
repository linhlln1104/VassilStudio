# VassilStudio Source Layout

VassilStudio is moving toward a DeerFlow-inspired workspace layout.

This style is best described as a workspace/monorepo application layout:

- root-level apps and concerns are visible immediately: `backend`, `frontend`, `contracts`, `docs`, `scripts`, `docker`.
- the backend stays a modular monolith, but app wiring is separated from reusable runtime code.
- the frontend is no longer hidden inside the Python package.
- model files, data, and local configs stay outside application code.

It is not a microservice layout. VassilStudio can still deploy as one FastAPI process while keeping a clearer source tree.

## Target Shape

```text
VassilStudio/
  backend/
    vvoice/
      main.py
      app/
        api/
        gateway/
      core/
        config.py
        container.py
        errors.py
      domains/
        asr/
        tts/
        voices/
        realtime/
      shared/
        audio/
        security/
      workers/
  frontend/
    studio-react/
      src/
      package.json
      vite.config.ts
    studio/
      legacy static UI fallback
  contracts/
    openapi/
    schemas/
  config/
  models/
    runtime/
    source/
  data/
  logs/
  docker/
  docs/
  scripts/
  tests/
    backend/
    frontend/
```

## Current Phase

The first phase keeps behavior stable and only improves the source boundaries:

```text
VassilStudio/
  backend/
    vvoice/
      main.py
      core/
      app/
      domains/
      shared/
  frontend/
    studio-react/
      src/
      dist/
    studio/
      legacy fallback
  models/
    runtime/
    source/
  data/
  logs/
  docker/
```

The backend now uses `domains` for voice capabilities, `shared` for cross-domain utilities, and
`app` for product-facing HTTP surfaces such as Studio and system status. The Studio route serves
the React build from `frontend/studio-react/dist` when available, with the legacy static UI kept as
a fallback during the transition.

## Migration Rules

- Move code before renaming concepts.
- Keep HTTP routes and public API behavior unchanged per phase.
- Run tests after each structural move.
- Avoid moving `models`, `data`, `logs`, or local config into source folders.
- Keep `models/runtime` as the only default model path used by runtime config.
- Keep the model runtime behind services so the API, jobs, and future CLI can reuse it.

## Naming

Recommended names for this architecture:

- repo level: workspace layout or monorepo-style application layout
- backend level: modular monolith
- module level: domain-oriented or feature-oriented modules
- runtime layer: engine/package layer

For VassilStudio, the useful mental model is:

```text
frontend studio -> backend gateway/API -> voice domains -> model runtime adapters -> ZipFormer/ZipVoice
```
