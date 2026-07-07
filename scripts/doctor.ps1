$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
  $Python = "python"
}

$BackendDir = Join-Path $Root "backend"
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$BackendDir;$env:PYTHONPATH" } else { $BackendDir }

& $Python (Join-Path $PSScriptRoot "doctor.py") @args
exit $LASTEXITCODE
