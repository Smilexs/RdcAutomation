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

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python was not found. Install Python 3.11+ for source development, or use the packaged rdc-auto.exe."
}

Invoke-Checked python -m pip install --upgrade pip
Invoke-Checked python -m pip install -e ".[dev]"
Invoke-Checked python -m pytest -v
