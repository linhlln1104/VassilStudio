param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

$DefaultConfig = Join-Path $root "config\vassil.example.json"
if (-not (Test-Path $DefaultConfig)) {
  $DefaultConfig = Join-Path $root "config\vvoice.example.json"
}
if (-not $env:VASSIL_CONFIG) {
  $env:VASSIL_CONFIG = if ($env:VVOICE_CONFIG) { $env:VVOICE_CONFIG } else { $DefaultConfig }
}
if (-not $env:VVOICE_CONFIG) {
  $env:VVOICE_CONFIG = $env:VASSIL_CONFIG
}
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$backendDir;$env:PYTHONPATH" } else { $backendDir }

& $Python -m uvicorn vvoice.main:create_app --factory --host 127.0.0.1 --port $Port --reload --reload-dir $backendDir --reload-dir $frontendDir
