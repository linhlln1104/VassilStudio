param(
  [int]$Port = 8018,
  [int]$TimeoutSeconds = 240,
  [switch]$SkipBuild,
  [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root "docker\docker-compose.yml"
$ProjectName = if ($env:VASSIL_DOCKER_PROJECT) {
  $env:VASSIL_DOCKER_PROJECT
} elseif ($env:VVOICE_DOCKER_PROJECT) {
  $env:VVOICE_DOCKER_PROJECT
} else {
  "vassil-smoke"
}
$PreviousPort = $env:VASSIL_PORT
$BaseUrl = "http://127.0.0.1:$Port"
$Started = $false

function Invoke-DockerCompose {
  param([string[]]$ComposeArgs)

  & docker @ComposeArgs
  if ($LASTEXITCODE -ne 0) {
    throw "docker command failed: docker $($ComposeArgs -join ' ')"
  }
}

function Assert-DockerDaemon {
  $Stdout = New-TemporaryFile
  $Stderr = New-TemporaryFile
  try {
    $Process = Start-Process `
      -FilePath "docker" `
      -ArgumentList @("info") `
      -Wait `
      -PassThru `
      -WindowStyle Hidden `
      -RedirectStandardOutput $Stdout `
      -RedirectStandardError $Stderr

    if ($Process.ExitCode -ne 0) {
      $Detail = (Get-Content -LiteralPath $Stderr -Raw).Trim()
      if (-not $Detail) {
        $Detail = "docker info exited with code $($Process.ExitCode)"
      }
      throw "Docker is installed, but the Docker daemon is not reachable. Start Docker Desktop or the Docker service, then rerun this smoke check. Detail: $Detail"
    }
  } finally {
    Remove-Item -LiteralPath $Stdout, $Stderr -Force -ErrorAction SilentlyContinue
  }
}

function Wait-ForHealth {
  param([string]$Url, [int]$Timeout)

  $Deadline = (Get-Date).AddSeconds($Timeout)
  do {
    try {
      $Health = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 5
      if ($Health.status -eq "ok") {
        return $Health
      }
    } catch {
      Start-Sleep -Seconds 2
    }
  } while ((Get-Date) -lt $Deadline)

  throw "Docker smoke server did not become healthy within $Timeout seconds"
}

try {
  Assert-DockerDaemon
  & (Join-Path $PSScriptRoot "setup_storage.ps1") | Out-Host

  $env:VASSIL_PORT = [string]$Port
  $BaseComposeArgs = @("compose", "-p", $ProjectName, "-f", $ComposeFile)
  $UpArgs = $BaseComposeArgs + @("up", "-d")
  if (-not $SkipBuild) {
    $UpArgs += "--build"
  }

  Write-Host "Starting Docker smoke project '$ProjectName' on $BaseUrl"
  Invoke-DockerCompose -ComposeArgs $UpArgs
  $Started = $true

  $Health = Wait-ForHealth -Url $BaseUrl -Timeout $TimeoutSeconds
  Write-Host "health:"
  $Health | ConvertTo-Json -Depth 8 | Write-Host

  $Status = Invoke-RestMethod -Uri "$BaseUrl/model-status" -TimeoutSec 10
  Write-Host "model-status:"
  $Status | ConvertTo-Json -Depth 8 | Write-Host
  if (-not $Status.ready) {
    throw "Docker model-status is not ready"
  }

  $Studio = Invoke-WebRequest -Uri "$BaseUrl/studio" -UseBasicParsing -TimeoutSec 10
  if ($Studio.StatusCode -ne 200) {
    throw "Studio returned HTTP $($Studio.StatusCode)"
  }

  if ($Studio.Content -notmatch "VassilStudio") {
    throw "Studio did not return the VassilStudio React shell"
  }

  $AssetMatches = [regex]::Matches($Studio.Content, '["''](/studio/assets/[^"'']+)["'']')
  if ($AssetMatches.Count -eq 0) {
    throw "Studio did not reference React build assets"
  }

  foreach ($Match in $AssetMatches) {
    $AssetPath = $Match.Groups[1].Value
    $Asset = Invoke-WebRequest -Uri "$BaseUrl$AssetPath" -UseBasicParsing -TimeoutSec 10
    if ($Asset.StatusCode -ne 200) {
      throw "Studio asset $AssetPath returned HTTP $($Asset.StatusCode)"
    }
  }

  Write-Host "Docker smoke check passed: $BaseUrl"
} finally {
  if ($Started) {
    if (-not $KeepRunning) {
      try {
        Invoke-DockerCompose -ComposeArgs (@("compose", "-p", $ProjectName, "-f", $ComposeFile, "down", "--remove-orphans"))
      } catch {
        Write-Warning $_.Exception.Message
      }
    } else {
      Write-Host "Keeping Docker smoke project running: $ProjectName"
    }
  }

  if ($null -eq $PreviousPort) {
    Remove-Item Env:\VASSIL_PORT -ErrorAction SilentlyContinue
  } else {
    $env:VASSIL_PORT = $PreviousPort
  }
}
