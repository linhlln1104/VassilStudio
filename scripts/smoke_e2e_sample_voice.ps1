$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
  $Python = "python"
}

$env:PYTHONIOENCODING = "utf-8"
& $Python (Join-Path $PSScriptRoot "smoke_e2e_sample_voice.py") @args
exit $LASTEXITCODE
