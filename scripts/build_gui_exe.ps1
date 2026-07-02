$ErrorActionPreference = "Stop"

function Invoke-Checked {
  $command = $args[0]
  $commandArgs = @()
  if ($args.Count -gt 1) {
    $commandArgs = $args[1..($args.Count - 1)]
  }

  & $command @commandArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $($args -join ' ')"
  }
}

Invoke-Checked python -m pip install -e ".[dev,gui]"
Invoke-Checked python -m pytest -v

$separator = [System.IO.Path]::PathSeparator
$addData = "rdc_auto\gui\static${separator}rdc_auto\gui\static"
$mcpSourceData = "renderdoc_mcp${separator}renderdoc_mcp"
$pyInstallerArgs = @(
  "--onefile",
  "--windowed",
  "--noupx",
  "--name", "RdcAutomation",
  "--collect-all", "webview",
  "--add-data", $addData,
  "--add-data", $mcpSourceData
)

Invoke-Checked python -m PyInstaller @pyInstallerArgs rdc_auto\gui\__main__.py

$exe = Join-Path $PWD "dist\RdcAutomation.exe"
if (-not (Test-Path $exe)) {
  throw "Expected executable was not produced: $exe"
}

Write-Host "Built $exe"
