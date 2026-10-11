param([string]$Config = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'local_env.ps1')
Import-LocalEnvFile (Join-Path $root '.env')
$Python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { $Python = 'python' }
if (-not $Config) {
    $Config = if ($env:VASSIL_CONFIG) { $env:VASSIL_CONFIG }
              elseif ($env:VVOICE_CONFIG) { $env:VVOICE_CONFIG }
              else { Join-Path $root 'config\vassil.example.json' }
}
$backendDir = Join-Path $root 'backend'
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$backendDir;$env:PYTHONPATH" } else { $backendDir }
& $Python -m vvoice.worker --config $Config
