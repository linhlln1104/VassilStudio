$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
  $Python = "python"
}

& $Python (Join-Path $PSScriptRoot "smoke_asr_job.py") @args
exit $LASTEXITCODE
