$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw 'Virtual environment not found. Run: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[runtime]"'
}

& $python (Join-Path $PSScriptRoot "smoke_tts.py") @args
exit $LASTEXITCODE
