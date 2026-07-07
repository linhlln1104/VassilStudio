$ErrorActionPreference = "Stop"

$baseUrl = if ($env:VASSIL_BASE_URL) {
    $env:VASSIL_BASE_URL
} elseif ($env:VVOICE_BASE_URL) {
    $env:VVOICE_BASE_URL
} else {
    "http://127.0.0.1:8000"
}
$apiKey = if ($env:VASSIL_API_KEY) { $env:VASSIL_API_KEY } else { $env:VVOICE_API_KEY }
$headers = @{}
if ($apiKey) {
    $headers["X-Vassil-API-Key"] = $apiKey
}

Write-Host "Checking $baseUrl/health"
$health = Invoke-RestMethod "$baseUrl/health"
$health | ConvertTo-Json -Depth 8

Write-Host "Checking $baseUrl/model-status"
$status = Invoke-RestMethod "$baseUrl/model-status" -Headers $headers
$status | ConvertTo-Json -Depth 8

if (-not $status.ready) {
    throw "Model status is not ready"
}
if ($status.runtime.asr_job_workers -lt 1 -or $status.runtime.tts_job_workers -lt 1) {
    throw "Job worker counts must be greater than zero"
}

Write-Host "VassilStudio API smoke check passed"
