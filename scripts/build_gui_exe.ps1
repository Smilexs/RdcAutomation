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
$pyInstallerArgs = @(
  "--onefile",
  "--windowed",
  "--name", "RdcAutomation",
  "--collect-all", "webview",
  "--add-data", $addData
)

$installerDir = Join-Path $PWD "installers"
if (Test-Path $installerDir) {
  $mcpInstallers = @(Get-ChildItem -Path $installerDir -Filter "RenderDocMCP-Setup-*.exe" -File)
  if ($mcpInstallers.Count -gt 0) {
    $installerAddData = "installers${separator}installers"
    $pyInstallerArgs += @("--add-data", $installerAddData)
    Write-Host "Bundling RenderDocMCP installer from $installerDir"
  } else {
    Write-Host "No installers\RenderDocMCP-Setup-*.exe found; MCP setup will fall back to GitHub."
  }
} else {
  Write-Host "No installers directory found; MCP setup will fall back to GitHub."
}

Invoke-Checked python -m PyInstaller @pyInstallerArgs rdc_auto\gui\__main__.py

$exe = Join-Path $PWD "dist\RdcAutomation.exe"
if (-not (Test-Path $exe)) {
  throw "Expected executable was not produced: $exe"
}

Write-Host "Built $exe"
