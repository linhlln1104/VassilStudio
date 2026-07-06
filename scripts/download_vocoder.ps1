$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root "models\runtime\tts\vi\zipvoice\vocos_24khz.onnx"
$url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/vocos_24khz.onnx"

if (Test-Path $target) {
    Write-Host "Already exists: $target"
    exit 0
}

New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
Write-Host "Downloading $url"
Invoke-WebRequest -UseBasicParsing $url -OutFile $target
Write-Host "Saved: $target"
