param([string]$Target = "")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }

$DownloadArguments = @((Join-Path $PSScriptRoot "download_vocoder.py"))
if ($Target) { $DownloadArguments += @("--target", $Target) }
& $Python @DownloadArguments
if ($LASTEXITCODE -ne 0) { throw "Vocoder download or integrity verification failed." }
