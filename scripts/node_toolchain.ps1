function Resolve-NodeToolchain {
  param([string]$NodePath = $env:VASSIL_NODE_PATH)

  $Candidates = @()
  if ($NodePath) {
    $Candidates += $NodePath
  } else {
    $NodeCommand = Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($NodeCommand) { $Candidates += $NodeCommand.Source }
    foreach ($Directory in @(
      $env:NVM_SYMLINK,
      $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles "nodejs" }),
      $(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "Programs\nodejs" }),
      $(if ($env:VOLTA_HOME) { Join-Path $env:VOLTA_HOME "bin" })
    )) {
      if ($Directory) { $Candidates += (Join-Path $Directory "node.exe") }
    }
  }

  foreach ($Candidate in $Candidates) {
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { continue }
    $ResolvedNode = (Resolve-Path -LiteralPath $Candidate).ProviderPath
    $NodeDirectory = Split-Path -Parent $ResolvedNode
    foreach ($NpmName in @("npm.cmd", "npm.exe", "npm")) {
      $NpmPath = Join-Path $NodeDirectory $NpmName
      if (Test-Path -LiteralPath $NpmPath -PathType Leaf) {
        # npm's child scripts resolve node from PATH, even when npm itself is absolute.
        $env:PATH = $NodeDirectory + [IO.Path]::PathSeparator + $env:PATH
        return @{ Node = $ResolvedNode; Npm = $NpmPath }
      }
    }
  }
  throw "Node.js 24 with npm was not found. Install Node.js or set VASSIL_NODE_PATH to node.exe."
}
