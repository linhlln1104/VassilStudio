# VassilStudio Contracts

This directory stores generated API contracts.

Generate the OpenAPI contract from the FastAPI app:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export_openapi.ps1
```

Default output:

```text
contracts/openapi/vassil.openapi.json
```

The export script also refreshes `contracts/openapi/vvoice.openapi.json` as a legacy contract path.
Regenerate these files whenever public API routes, request fields, or response shapes change.
