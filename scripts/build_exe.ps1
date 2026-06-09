$ErrorActionPreference = "Stop"

python -m pip install -e ".[dev]"
python -m pytest -v
python -m PyInstaller --onefile --name rdc-auto --console rdc_auto\__main__.py

$exe = Join-Path $PWD "dist\rdc-auto.exe"
if (-not (Test-Path $exe)) {
  throw "Expected executable was not produced: $exe"
}

Write-Host "Built $exe"
