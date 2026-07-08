param(
  [switch]$SkipDoctor,
  [switch]$SkipOpenApi,
  [switch]$SkipNode,
  [switch]$SkipCompose,
  [switch]$RunE2E,
  [switch]$RunLanguageMatrix,
  [switch]$RunDocker,
  [int]$DockerPort = 8018
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
  $Python = "python"
}

$BackendDir = Join-Path $Root "backend"
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$BackendDir;$env:PYTHONPATH" } else { $BackendDir }

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Script
  )

  Write-Host ""
  Write-Host "==> $Name"
  $global:LASTEXITCODE = 0
  & $Script
  if (-not $?) {
    throw "Step failed: $Name"
  }
  if ($LASTEXITCODE -ne 0) {
    throw "Step failed: $Name"
  }
}

function Test-CommandAvailable {
  param([string]$Command)

  return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Get-NpmCommand {
  if (Test-CommandAvailable "npm.cmd") {
    return "npm.cmd"
  }

  if (Test-CommandAvailable "npm") {
    return "npm"
  }

  return $null
}

Invoke-Step "setup storage" {
  & (Join-Path $PSScriptRoot "setup_storage.ps1")
}

if (-not $SkipDoctor) {
  Invoke-Step "doctor" {
    & $Python (Join-Path $PSScriptRoot "doctor.py")
  }
}

if (-not $SkipOpenApi) {
  Invoke-Step "export openapi" {
    & $Python (Join-Path $PSScriptRoot "export_openapi.py")
  }
}

Invoke-Step "ruff" {
  & $Python -m ruff check backend scripts tests
}

if (-not $SkipNode) {
  if (-not (Test-CommandAvailable "node")) {
    throw "Node.js is required for frontend syntax checks. Install node or rerun with -SkipNode."
  }

  $Npm = Get-NpmCommand
  if (-not $Npm) {
    throw "npm is required for React Studio checks. Install npm or rerun with -SkipNode."
  }

  $StudioReact = Join-Path $Root "frontend\studio-react"
  if (-not (Test-Path (Join-Path $StudioReact "node_modules"))) {
    Invoke-Step "studio-react npm ci" {
      Push-Location $StudioReact
      try {
        & $Npm ci
      } finally {
        Pop-Location
      }
    }
  }

  Invoke-Step "studio-react lint" {
    Push-Location $StudioReact
    try {
      & $Npm run lint
    } finally {
      Pop-Location
    }
  }

  Invoke-Step "studio-react build" {
    Push-Location $StudioReact
    try {
      & $Npm run build
    } finally {
      Pop-Location
    }
  }

  $FrontendFiles = @(
    "frontend\studio\app.js",
    "frontend\studio\src\api.js",
    "frontend\studio\src\http.js",
    "frontend\studio\src\state.js",
    "frontend\studio\src\ui.js"
  )

  foreach ($RelativePath in $FrontendFiles) {
    Invoke-Step "node --check $RelativePath" {
      & node --check (Join-Path $Root $RelativePath)
    }
  }
}

Invoke-Step "pytest" {
  & $Python -m pytest
}

Invoke-Step "auth/product smoke" {
  & $Python (Join-Path $PSScriptRoot "smoke_auth.py")
}

if (-not $SkipCompose) {
  if (-not (Test-CommandAvailable "docker")) {
    throw "Docker CLI is required for compose config validation. Install Docker or rerun with -SkipCompose."
  }

  Invoke-Step "docker compose config" {
    $PreviousPort = $env:VASSIL_PORT
    try {
      $env:VASSIL_PORT = [string]$DockerPort
      & docker compose -p vassil-check -f (Join-Path $Root "docker\docker-compose.yml") config --quiet
    } finally {
      if ($null -eq $PreviousPort) {
        Remove-Item Env:\VASSIL_PORT -ErrorAction SilentlyContinue
      } else {
        $env:VASSIL_PORT = $PreviousPort
      }
    }
  }
}

if ($RunE2E) {
  Invoke-Step "E2E sample voice smoke" {
    & $Python (Join-Path $PSScriptRoot "smoke_e2e_sample_voice.py")
  }
}

if ($RunLanguageMatrix) {
  Invoke-Step "VI/EN language matrix smoke" {
    & $Python (Join-Path $PSScriptRoot "smoke_language_matrix.py")
  }
}

if ($RunDocker) {
  Invoke-Step "Docker smoke" {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "smoke_docker.ps1") -Port $DockerPort
  }
}

Write-Host ""
Write-Host "VassilStudio check passed"
