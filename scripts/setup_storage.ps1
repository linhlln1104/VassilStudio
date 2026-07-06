$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

$dirs = @(
  "models\runtime\asr\vi\zipformer",
  "models\runtime\tts\vi\zipvoice",
  "models\source",
  "data\voices",
  "data\jobs\asr",
  "data\jobs\tts",
  "data\uploads",
  "data\outputs",
  "logs",
  "docker"
)

foreach ($relative in $dirs) {
  $path = Join-Path $root $relative
  New-Item -ItemType Directory -Path $path -Force | Out-Null
  Write-Host "OK $relative"
}

$legacyZipmodel = Join-Path $root "Zipmodel"
if (Test-Path $legacyZipmodel) {
  Write-Host "NOTE Zipmodel exists as a legacy drop folder. Runtime config uses models\runtime by default."
}
