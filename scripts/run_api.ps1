param(
  [int]$Port = 8000,
  [string]$BindAddress = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

function Import-LocalEnvFile {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    return
  }

  foreach ($RawLine in Get-Content -Path $Path) {
    $Line = $RawLine.Trim()
    if (-not $Line -or $Line.StartsWith("#")) {
      continue
    }

    $Separator = $Line.IndexOf("=")
    if ($Separator -lt 1) {
      continue
    }

    $Name = $Line.Substring(0, $Separator).Trim()
    $Value = $Line.Substring($Separator + 1).Trim()
    if (
      ($Value.StartsWith('"') -and $Value.EndsWith('"')) -or
      ($Value.StartsWith("'") -and $Value.EndsWith("'"))
    ) {
      $Value = $Value.Substring(1, $Value.Length - 2)
    }

    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
      [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
  }
}

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

& $Python -m uvicorn vvoice.main:create_app --factory --host $BindAddress --port $Port --reload --reload-dir $backendDir --reload-dir $frontendDir
