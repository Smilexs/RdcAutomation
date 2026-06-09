$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python was not found. Install Python 3.11+ for source development, or use the packaged rdc-auto.exe."
}

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -v
