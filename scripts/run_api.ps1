param(
  [int]$Port = 8000,
  [string]$BindAddress = "",
  [switch]$Reload
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

. (Join-Path $PSScriptRoot "local_env.ps1")

Import-LocalEnvFile (Join-Path $root ".env")

if (-not $BindAddress) {
  $BindAddress = if ($env:VASSIL_BIND_ADDRESS) {
    $env:VASSIL_BIND_ADDRESS
  } elseif ($env:VVOICE_BIND_ADDRESS) {
    $env:VVOICE_BIND_ADDRESS
  } else {
    "127.0.0.1"
  }
}
$env:VASSIL_BIND_ADDRESS = $BindAddress

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

if ($Reload) {
  & $Python -m uvicorn vvoice.main:create_app --factory --host $BindAddress --port $Port --no-access-log --reload --reload-dir $backendDir --reload-dir $frontendDir
} else {
  & $Python -m uvicorn vvoice.main:create_app --factory --host $BindAddress --port $Port --no-access-log
}
