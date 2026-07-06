$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root "docker\docker-compose.yml"

& (Join-Path $PSScriptRoot "setup_storage.ps1")
docker compose -f $composeFile up --build
