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

Invoke-Checked python -m pip install -e ".[dev]"
Invoke-Checked python -m pytest -v
Invoke-Checked python -m PyInstaller --onefile --name rdc-auto --console rdc_auto\__main__.py

$exe = Join-Path $PWD "dist\rdc-auto.exe"
if (-not (Test-Path $exe)) {
  throw "Expected executable was not produced: $exe"
}

Write-Host "Built $exe"
