# rdc-auto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `rdc-auto` Windows CLI and Codex Skill for RenderDoc v1.44 + RenderDocMCP + MuMu12 Vulkan capture, then export textures and meshes from `.rdc` files.

**Architecture:** The CLI is a Python package with focused modules for configuration, dependency setup, MuMu12 process checks, installed RenderDocMCP executable management, capture orchestration, export orchestration, and mesh conversion. The Codex Skill remains thin and maps user intent to `rdc-auto setup`, `rdc-auto attach`, `rdc-auto capture`, and `rdc-auto export`.

**Tech Stack:** Python 3.11+, stdlib `argparse`/`json`/`subprocess`/`urllib`, pytest, PyInstaller, PowerShell bootstrap, Codex Skill Markdown.

---

## Repository Root

All paths are relative to:

```text
E:\ZSGame\AIProjects\RdcAutomation
```

## File Structure

Create this structure:

```text
pyproject.toml
rdc_auto/
  __init__.py
  __main__.py
  cli.py
  config.py
  errors.py
  paths.py
  prompts.py
  log_setup.py
  renderdoc_installer.py
  mcp_installer.py
  mcp_client.py
  emulator.py
  capture.py
  export_assets.py
  mesh_convert.py
scripts/
  bootstrap.ps1
  build_exe.ps1
skills/
  rdc-auto/
    SKILL.md
    agents/
      openai.yaml
tests/
  conftest.py
  test_config.py
  test_paths_emulator.py
  test_renderdoc_installer.py
  test_mcp_client.py
  test_capture_service.py
  test_mesh_convert.py
  test_export_assets.py
  test_cli.py
```

Boundary decisions:

- `rdc_auto.mcp_installer` downloads the latest Windows release asset from `https://api.github.com/repos/Smilexs/RenderDocMCP/releases/latest`, installs `RenderDocMCP-Setup-*.exe`, records the installed MCP executable path, and does not clone the source repository.
- `rdc_auto.mcp_client.FileIpcMcpClient` starts the installed RenderDocMCP executable when needed, then talks to the RenderDocMCP bridge file IPC under `%TEMP%\renderdoc_mcp`.
- Session lifecycle methods (`launch_application`, `get_target_status`, `trigger_capture`, `close_target`) are treated as required MCP bridge capabilities. The CLI fails with a clear message if the installed RenderDocMCP does not expose them.

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `rdc_auto/__init__.py`
- Create: `rdc_auto/__main__.py`
- Create: `rdc_auto/errors.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the failing package import test**

Create `tests/conftest.py`:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "LocalAppData")
    env["TEMP"] = str(tmp_path / "Temp")
    env["TMP"] = str(tmp_path / "Temp")
    return env
```

Create `tests/test_cli.py`:

```python
from __future__ import annotations


def test_package_exposes_version():
    import rdc_auto

    assert isinstance(rdc_auto.__version__, str)
    assert rdc_auto.__version__
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_cli.py::test_package_exposes_version -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rdc_auto'`.

- [ ] **Step 3: Create the Python package scaffold**

Create `pyproject.toml`:

```toml
[project]
name = "rdc-auto"
version = "0.1.0"
description = "RenderDoc automation for MuMu12 capture and asset export"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
rdc-auto = "rdc_auto.cli:main"

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pyinstaller>=6.0"
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `rdc_auto/__init__.py`:

```python
from __future__ import annotations

__version__ = "0.1.0"
```

Create `rdc_auto/__main__.py`:

```python
from __future__ import annotations

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `rdc_auto/errors.py`:

```python
from __future__ import annotations


class RdcAutoError(Exception):
    """Base exception for expected rdc-auto failures."""


class UserActionRequired(RdcAutoError):
    """Raised when the CLI must ask the user before continuing."""


class DependencyMissing(RdcAutoError):
    """Raised when a required local dependency cannot be found."""


class McpCapabilityMissing(RdcAutoError):
    """Raised when RenderDocMCP does not expose a required tool."""
```

Create a temporary minimal `rdc_auto/cli.py`:

```python
from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
python -m pytest tests/test_cli.py::test_package_exposes_version -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml rdc_auto tests
git commit -m "chore: scaffold rdc-auto package"
```

---

### Task 2: Configuration Store

**Files:**
- Create: `rdc_auto/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from rdc_auto.config import AppConfig, config_path, load_config, save_config


def test_config_path_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    assert config_path() == tmp_path / "LocalAppData" / "RdcAutomation" / "config.json"


def test_load_config_returns_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    cfg = load_config()

    assert cfg.renderdoc.version == "1.44"
    assert cfg.mcp.release_api_url == "https://api.github.com/repos/Smilexs/RenderDocMCP/releases/latest"
    assert cfg.mcp.asset_name == ""
    assert cfg.mcp.executable_path == ""
    assert cfg.emulator.type == "mumu12"
    assert cfg.emulator.exe_relative_path == "MuMuPlayer-12.0\\nx_main\\MuMuNxMain.exe"
    assert cfg.emulator.graphics_api == "vulkan"


def test_save_and_reload_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    cfg = AppConfig.default()
    cfg.emulator.root_dir = "D:\\MuMu"
    cfg.capture.last_output_dir = "D:\\Captures"

    save_config(cfg)
    loaded = load_config()

    assert loaded.emulator.root_dir == "D:\\MuMu"
    assert loaded.capture.last_output_dir == "D:\\Captures"
    data = json.loads(config_path().read_text(encoding="utf-8"))
    assert data["emulator"]["graphics_api"] == "vulkan"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_config.py -v
```

Expected: FAIL because `rdc_auto.config` does not exist.

- [ ] **Step 3: Implement config dataclasses and JSON persistence**

Create `rdc_auto/config.py`:

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


APP_DIR_NAME = "RdcAutomation"
MCP_RELEASE_API_URL = "https://api.github.com/repos/Smilexs/RenderDocMCP/releases/latest"
MUMU_RELATIVE_EXE = "MuMuPlayer-12.0\\nx_main\\MuMuNxMain.exe"


@dataclass
class RenderDocConfig:
    version: str = "1.44"
    install_dir: str = ""
    qrenderdoc_path: str = ""
    renderdoccmd_path: str = ""


@dataclass
class McpConfig:
    release_api_url: str = MCP_RELEASE_API_URL
    asset_name: str = ""
    installer_path: str = ""
    install_dir: str = ""
    executable_path: str = ""
    mode: str = "managed"


@dataclass
class EmulatorConfig:
    type: str = "mumu12"
    root_dir: str = ""
    exe_relative_path: str = MUMU_RELATIVE_EXE
    graphics_api: str = "vulkan"


@dataclass
class CaptureConfig:
    last_output_dir: str = ""
    last_rdc_path: str = ""
    active_session_id: str | None = None
    active_pid: int | None = None


@dataclass
class AppConfig:
    renderdoc: RenderDocConfig = field(default_factory=RenderDocConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    emulator: EmulatorConfig = field(default_factory=EmulatorConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)

    @classmethod
    def default(cls) -> "AppConfig":
        cfg = cls()
        app_dir = app_data_dir()
        cfg.mcp.install_dir = str(app_dir / "mcp")
        return cfg


def app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME


def log_dir() -> Path:
    return app_data_dir() / "logs"


def config_path() -> Path:
    return app_data_dir() / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    path = path or config_path()
    if not path.exists():
        return AppConfig.default()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _from_dict(raw)


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _from_dict(raw: dict[str, Any]) -> AppConfig:
    default = AppConfig.default()
    return AppConfig(
        renderdoc=RenderDocConfig(**{**asdict(default.renderdoc), **raw.get("renderdoc", {})}),
        mcp=McpConfig(**{**asdict(default.mcp), **raw.get("mcp", {})}),
        emulator=EmulatorConfig(**{**asdict(default.emulator), **raw.get("emulator", {})}),
        capture=CaptureConfig(**{**asdict(default.capture), **raw.get("capture", {})}),
    )
```

- [ ] **Step 4: Run config tests**

Run:

```powershell
python -m pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/config.py tests/test_config.py
git commit -m "feat: add rdc-auto config store"
```

---

### Task 3: Logging and Interactive Prompts

**Files:**
- Create: `rdc_auto/log_setup.py`
- Create: `rdc_auto/prompts.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for prompt helpers**

Append to `tests/test_cli.py`:

```python
from pathlib import Path

from rdc_auto.prompts import choose_option, prompt_path


def test_choose_option_accepts_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert choose_option("Asset type", ["textures", "meshes", "both"], default="both") == "both"


def test_choose_option_accepts_number(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "2")

    assert choose_option("Asset type", ["textures", "meshes", "both"], default="both") == "meshes"


def test_prompt_path_returns_default(monkeypatch, tmp_path):
    default = tmp_path / "captures"
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert prompt_path("Output directory", default=default) == default
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `rdc_auto.prompts` does not exist.

- [ ] **Step 3: Implement prompt and logging helpers**

Create `rdc_auto/prompts.py`:

```python
from __future__ import annotations

from pathlib import Path


def prompt_text(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def prompt_path(label: str, default: str | Path | None = None) -> Path:
    default_text = str(default) if default else ""
    value = prompt_text(label, default_text)
    return Path(value).expanduser()


def choose_option(label: str, options: list[str], default: str | None = None) -> str:
    if not options:
        raise ValueError("options must not be empty")
    if default is not None and default not in options:
        raise ValueError("default must be one of options")

    print(label)
    for index, option in enumerate(options, start=1):
        marker = " default" if option == default else ""
        print(f"  {index}. {option}{marker}")

    while True:
        raw = input("Select option: ").strip()
        if raw == "" and default is not None:
            return default
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        if raw in options:
            return raw
        print(f"Enter a number from 1 to {len(options)} or one of: {', '.join(options)}")
```

Create `rdc_auto/log_setup.py`:

```python
from __future__ import annotations

import logging
from pathlib import Path

from .config import log_dir


def configure_logging(verbose: bool = False, directory: Path | None = None) -> Path:
    directory = directory or log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "rdc-auto.log"
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    return log_path
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/prompts.py rdc_auto/log_setup.py tests/test_cli.py
git commit -m "feat: add prompts and logging helpers"
```

---

### Task 4: Path Resolution and MuMu12 Process Checks

**Files:**
- Create: `rdc_auto/paths.py`
- Create: `rdc_auto/emulator.py`
- Create: `tests/test_paths_emulator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_paths_emulator.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rdc_auto.config import AppConfig
from rdc_auto.emulator import EmulatorProcess, MuMu12
from rdc_auto.paths import mumu_exe_path, validate_mumu_root


def test_mumu_exe_path_uses_fixed_relative_path():
    assert mumu_exe_path(Path("D:/MuMu")) == Path("D:/MuMu/MuMuPlayer-12.0/nx_main/MuMuNxMain.exe")


def test_validate_mumu_root_accepts_existing_exe(tmp_path):
    exe = tmp_path / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    assert validate_mumu_root(tmp_path) == exe


def test_validate_mumu_root_rejects_missing_exe(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_mumu_root(tmp_path)


def test_emulator_running_detects_tasklist_csv():
    calls = []

    def runner(args, capture_output, text, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout='"Image Name","PID"\\n"MuMuNxMain.exe","1234"\\n')

    proc = EmulatorProcess(runner=runner)

    assert proc.is_running("MuMuNxMain.exe") is True
    assert calls[0][0] == "tasklist"


def test_mumu12_resolve_updates_config(tmp_path):
    exe = tmp_path / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path)

    mumu = MuMu12(cfg)

    assert mumu.executable() == exe
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_paths_emulator.py -v
```

Expected: FAIL because `paths.py` and `emulator.py` do not exist.

- [ ] **Step 3: Implement paths and emulator helpers**

Create `rdc_auto/paths.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

from .config import MUMU_RELATIVE_EXE


def mumu_exe_path(root: str | Path) -> Path:
    return Path(root) / Path(MUMU_RELATIVE_EXE)


def validate_mumu_root(root: str | Path) -> Path:
    exe = mumu_exe_path(root)
    if not exe.is_file():
        raise FileNotFoundError(f"MuMu12 executable not found: {exe}")
    return exe


def find_renderdoc_install() -> dict[str, str]:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "RenderDoc",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "RenderDoc",
    ]
    for install_dir in candidates:
        qrenderdoc = install_dir / "qrenderdoc.exe"
        renderdoccmd = install_dir / "renderdoccmd.exe"
        if qrenderdoc.is_file():
            return {
                "install_dir": str(install_dir),
                "qrenderdoc_path": str(qrenderdoc),
                "renderdoccmd_path": str(renderdoccmd) if renderdoccmd.is_file() else "",
            }
    return {"install_dir": "", "qrenderdoc_path": "", "renderdoccmd_path": ""}
```

Create `rdc_auto/emulator.py`:

```python
from __future__ import annotations

import csv
import subprocess
from io import StringIO
from pathlib import Path
from typing import Callable

from .config import AppConfig
from .paths import validate_mumu_root


Runner = Callable[..., subprocess.CompletedProcess[str]]


class EmulatorProcess:
    def __init__(self, runner: Runner = subprocess.run):
        self._runner = runner

    def is_running(self, image_name: str) -> bool:
        result = self._runner(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
        )
        rows = csv.DictReader(StringIO(result.stdout))
        for row in rows:
            if row.get("Image Name", "").lower() == image_name.lower():
                return True
        return False

    def terminate_tree(self, image_name: str) -> None:
        self._runner(["taskkill", "/IM", image_name, "/T", "/F"], capture_output=True, text=True, check=False)


class MuMu12:
    image_name = "MuMuNxMain.exe"

    def __init__(self, config: AppConfig, process: EmulatorProcess | None = None):
        self.config = config
        self.process = process or EmulatorProcess()

    def executable(self) -> Path:
        if not self.config.emulator.root_dir:
            raise FileNotFoundError("MuMu12 root directory is not configured")
        return validate_mumu_root(self.config.emulator.root_dir)

    def is_running(self) -> bool:
        return self.process.is_running(self.image_name)

    def terminate(self) -> None:
        self.process.terminate_tree(self.image_name)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_paths_emulator.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/paths.py rdc_auto/emulator.py tests/test_paths_emulator.py
git commit -m "feat: add MuMu12 path and process checks"
```

---

### Task 5: RenderDoc v1.44 Installer

**Files:**
- Create: `rdc_auto/renderdoc_installer.py`
- Create: `tests/test_renderdoc_installer.py`

- [ ] **Step 1: Write failing installer tests**

Create `tests/test_renderdoc_installer.py`:

```python
from __future__ import annotations

import subprocess

from rdc_auto.config import AppConfig
from rdc_auto.renderdoc_installer import RenderDocInstaller, parse_v144_windows_x64_url


def test_parse_v144_windows_x64_url_from_builds_html():
    html = """
    <a href="/stable/1.44/RenderDoc_1.44_64.msi">Windows 64-bit installer</a>
    <a href="/stable/1.43/RenderDoc_1.43_64.msi">Older installer</a>
    """

    assert parse_v144_windows_x64_url(html) == "https://renderdoc.org/stable/1.44/RenderDoc_1.44_64.msi"


def test_parse_v144_windows_x64_url_accepts_absolute_url():
    html = '<a href="https://renderdoc.org/stable/1.44/RenderDoc_1.44_64.exe">Windows 64-bit installer</a>'

    assert parse_v144_windows_x64_url(html) == "https://renderdoc.org/stable/1.44/RenderDoc_1.44_64.exe"


def test_installer_updates_config_when_existing_renderdoc_found(tmp_path):
    qrenderdoc = tmp_path / "RenderDoc" / "qrenderdoc.exe"
    renderdoccmd = tmp_path / "RenderDoc" / "renderdoccmd.exe"
    qrenderdoc.parent.mkdir()
    qrenderdoc.write_text("", encoding="utf-8")
    renderdoccmd.write_text("", encoding="utf-8")
    cfg = AppConfig.default()

    installer = RenderDocInstaller(
        config=cfg,
        finder=lambda: {
            "install_dir": str(qrenderdoc.parent),
            "qrenderdoc_path": str(qrenderdoc),
            "renderdoccmd_path": str(renderdoccmd),
        },
    )

    assert installer.ensure_installed() is True
    assert cfg.renderdoc.qrenderdoc_path == str(qrenderdoc)
    assert cfg.renderdoc.renderdoccmd_path == str(renderdoccmd)


def test_run_installer_uses_default_options(tmp_path):
    installer_file = tmp_path / "RenderDoc_1.44_64.msi"
    installer_file.write_text("", encoding="utf-8")
    calls = []

    def runner(args, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    installer = RenderDocInstaller(config=AppConfig.default(), runner=runner)
    installer.run_installer(installer_file)

    assert calls == [["msiexec", "/i", str(installer_file), "/passive"]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_renderdoc_installer.py -v
```

Expected: FAIL because `rdc_auto.renderdoc_installer` does not exist.

- [ ] **Step 3: Implement RenderDoc installer helpers**

Create `rdc_auto/renderdoc_installer.py`:

```python
from __future__ import annotations

import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable

from .config import AppConfig, app_data_dir
from .paths import find_renderdoc_install


BUILDS_URL = "https://renderdoc.org/builds"
RENDERDOC_VERSION = "1.44"


def parse_v144_windows_x64_url(html: str) -> str:
    hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    for href in hrefs:
        lower = href.lower()
        if "1.44" in lower and ("_64" in lower or "x64" in lower) and (lower.endswith(".msi") or lower.endswith(".exe")):
            if href.startswith("http://") or href.startswith("https://"):
                return href
            if href.startswith("/"):
                return "https://renderdoc.org" + href
            return "https://renderdoc.org/" + href
    raise ValueError("RenderDoc v1.44 Windows x64 installer link was not found")


class RenderDocInstaller:
    def __init__(
        self,
        config: AppConfig,
        finder: Callable[[], dict[str, str]] = find_renderdoc_install,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ):
        self.config = config
        self.finder = finder
        self.runner = runner

    def ensure_installed(self) -> bool:
        found = self.finder()
        if found.get("qrenderdoc_path"):
            self.config.renderdoc.version = RENDERDOC_VERSION
            self.config.renderdoc.install_dir = found.get("install_dir", "")
            self.config.renderdoc.qrenderdoc_path = found.get("qrenderdoc_path", "")
            self.config.renderdoc.renderdoccmd_path = found.get("renderdoccmd_path", "")
            return True
        return False

    def resolve_download_url(self) -> str:
        with urllib.request.urlopen(BUILDS_URL, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
        return parse_v144_windows_x64_url(html)

    def download_installer(self, url: str) -> Path:
        downloads = app_data_dir() / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        filename = url.rstrip("/").split("/")[-1] or "RenderDoc_1.44_64_installer.exe"
        target = downloads / filename
        urllib.request.urlretrieve(url, target)
        return target

    def run_installer(self, installer_path: Path) -> None:
        suffix = installer_path.suffix.lower()
        if suffix == ".msi":
            self.runner(["msiexec", "/i", str(installer_path), "/passive"], check=True)
            return
        self.runner([str(installer_path)], check=True)
```

- [ ] **Step 4: Run installer tests**

Run:

```powershell
python -m pytest tests/test_renderdoc_installer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/renderdoc_installer.py tests/test_renderdoc_installer.py
git commit -m "feat: add RenderDoc v1.44 installer support"
```

---

### Task 6: RenderDocMCP Release Installer

**Files:**
- Create: `rdc_auto/mcp_installer.py`
- Create: `tests/test_mcp_installer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_mcp_installer.py`:

```python
from __future__ import annotations

import subprocess

from rdc_auto.config import AppConfig
from rdc_auto.mcp_installer import McpInstaller, parse_release_asset


def test_parse_release_asset_picks_setup_exe():
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {"name": "source.zip", "browser_download_url": "https://example/source.zip"},
            {
                "name": "RenderDocMCP-Setup-1.0.0.exe",
                "browser_download_url": "https://example/RenderDocMCP-Setup-1.0.0.exe",
                "digest": "sha256:abc123",
            },
        ],
    }

    asset = parse_release_asset(release)

    assert asset.name == "RenderDocMCP-Setup-1.0.0.exe"
    assert asset.download_url == "https://example/RenderDocMCP-Setup-1.0.0.exe"
    assert asset.digest == "sha256:abc123"


def test_download_latest_installer_records_release_asset(tmp_path):
    cfg = AppConfig.default()
    cfg.mcp.install_dir = str(tmp_path / "mcp")
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {
                "name": "RenderDocMCP-Setup-1.0.0.exe",
                "browser_download_url": "https://example/RenderDocMCP-Setup-1.0.0.exe",
                "digest": "sha256:abc123",
            }
        ],
    }

    def fetch_json(url):
        assert url == cfg.mcp.release_api_url
        return release

    def downloader(url, target):
        assert url == "https://example/RenderDocMCP-Setup-1.0.0.exe"
        target.write_bytes(b"exe")

    installer = McpInstaller(cfg, fetch_json=fetch_json, downloader=downloader)
    path = installer.download_latest_installer()

    assert path == tmp_path / "mcp" / "downloads" / "RenderDocMCP-Setup-1.0.0.exe"
    assert cfg.mcp.asset_name == "RenderDocMCP-Setup-1.0.0.exe"
    assert cfg.mcp.installer_path == str(path)


def test_run_installer_executes_downloaded_exe(tmp_path):
    setup = tmp_path / "RenderDocMCP-Setup-1.0.0.exe"
    setup.write_bytes(b"exe")
    calls = []
    cfg = AppConfig.default()

    def runner(args, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    installer = McpInstaller(cfg, runner=runner)
    installer.run_installer(setup)

    assert calls == [[str(setup)]]


def test_discover_executable_prefers_configured_path(tmp_path):
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.mcp.executable_path = str(exe)

    installer = McpInstaller(cfg)

    assert installer.discover_executable() == exe
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mcp_installer.py -v
```

Expected: FAIL because `mcp_installer.py` does not exist.

- [ ] **Step 3: Implement release installer**

Create `rdc_auto/mcp_installer.py`:

```python
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import urllib.request

from .config import AppConfig, app_data_dir


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    digest: str = ""


def parse_release_asset(release: dict) -> ReleaseAsset:
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        lower = name.lower()
        if lower.endswith(".exe") and "setup" in lower:
            return ReleaseAsset(
                name=name,
                download_url=str(asset["browser_download_url"]),
                digest=str(asset.get("digest", "")),
            )
    raise ValueError("No RenderDocMCP setup .exe asset was found in the latest release")


JsonFetcher = Callable[[str], dict]
Downloader = Callable[[str, Path], object]
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


class McpInstaller:
    def __init__(
        self,
        config: AppConfig,
        fetch_json: JsonFetcher | None = None,
        downloader: Callable[[str, Path], object] | None = None,
        runner: Runner = subprocess.run,
    ):
        self.config = config
        self.fetch_json = fetch_json or self._fetch_json
        self.downloader = downloader or self._download
        self.runner = runner

    @staticmethod
    def _fetch_json(url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": "rdc-auto"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _download(url: str, target: Path) -> object:
        target.parent.mkdir(parents=True, exist_ok=True)
        return urllib.request.urlretrieve(url, target)

    def download_latest_installer(self) -> Path:
        release = self.fetch_json(self.config.mcp.release_api_url)
        asset = parse_release_asset(release)
        downloads = Path(self.config.mcp.install_dir or app_data_dir() / "mcp") / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        target = downloads / asset.name
        self.downloader(asset.download_url, target)
        self.config.mcp.asset_name = asset.name
        self.config.mcp.installer_path = str(target)
        return target

    def run_installer(self, installer_path: Path) -> None:
        self.runner([str(installer_path)], check=True)

    def discover_executable(self) -> Path | None:
        configured = Path(self.config.mcp.executable_path) if self.config.mcp.executable_path else None
        if configured and configured.is_file():
            return configured

        candidates = []
        install_dir = Path(self.config.mcp.install_dir) if self.config.mcp.install_dir else app_data_dir() / "mcp"
        for root in [
            install_dir,
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "RenderDocMCP",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "RenderDocMCP",
        ]:
            if str(root):
                candidates.extend([root / "RenderDocMCP.exe", root / "renderdoc-mcp.exe"])

        for candidate in candidates:
            if candidate.is_file():
                self.config.mcp.executable_path = str(candidate)
                return candidate
        return None

    def ensure_installed(self) -> Path:
        existing = self.discover_executable()
        if existing:
            return existing
        installer = self.download_latest_installer()
        self.run_installer(installer)
        found = self.discover_executable()
        if not found:
            raise FileNotFoundError("RenderDocMCP installed, but its executable was not found. Set mcp.executable_path in config.json.")
        return found
```

- [ ] **Step 4: Run MCP installer tests**

Run:

```powershell
python -m pytest tests/test_mcp_installer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/mcp_installer.py tests/test_mcp_installer.py
git commit -m "feat: install RenderDocMCP from release exe"
```

---

### Task 7: RenderDocMCP Bridge Client

**Files:**
- Create: `rdc_auto/mcp_client.py`
- Create: `tests/test_mcp_client.py`

- [ ] **Step 1: Write failing MCP client tests**

Create `tests/test_mcp_client.py`:

```python
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from rdc_auto.errors import McpCapabilityMissing
from rdc_auto.mcp_client import FileIpcMcpClient


def test_file_ipc_client_writes_request_and_reads_response(tmp_path):
    ipc = tmp_path / "renderdoc_mcp"
    client = FileIpcMcpClient(ipc_dir=ipc, poll_interval=0.01, timeout=1.0)

    def responder():
        request_path = ipc / "request.json"
        response_path = ipc / "response.json"
        while not request_path.exists():
            time.sleep(0.01)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request_path.unlink()
        response_path.write_text(json.dumps({"id": request["id"], "result": {"status": "ok"}}), encoding="utf-8")

    thread = threading.Thread(target=responder)
    thread.start()
    result = client.call("ping")
    thread.join(timeout=1)

    assert result == {"status": "ok"}


def test_file_ipc_client_raises_for_missing_method(tmp_path):
    ipc = tmp_path / "renderdoc_mcp"
    client = FileIpcMcpClient(ipc_dir=ipc, poll_interval=0.01, timeout=1.0)

    def responder():
        request_path = ipc / "request.json"
        response_path = ipc / "response.json"
        while not request_path.exists():
            time.sleep(0.01)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request_path.unlink()
        response_path.write_text(
            json.dumps({"id": request["id"], "error": {"code": -32601, "message": "Method not found: launch_application"}}),
            encoding="utf-8",
        )

    thread = threading.Thread(target=responder)
    thread.start()
    with pytest.raises(McpCapabilityMissing):
        client.call("launch_application")
    thread.join(timeout=1)


def test_client_starts_installed_executable_once(tmp_path):
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    starts = []

    def popen(args, **kwargs):
        starts.append(args)
        return subprocess.CompletedProcess(args, 0)

    client = FileIpcMcpClient(ipc_dir=tmp_path / "renderdoc_mcp", executable_path=exe, popen=popen)

    client.ensure_started()
    client.ensure_started()

    assert starts == [[str(exe)]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_mcp_client.py -v
```

Expected: FAIL because `rdc_auto.mcp_client` does not exist.

- [ ] **Step 3: Implement file IPC MCP client**

Create `rdc_auto/mcp_client.py`:

```python
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .errors import McpCapabilityMissing, RdcAutoError


class FileIpcMcpClient:
    def __init__(
        self,
        ipc_dir: Path | None = None,
        executable_path: str | Path | None = None,
        popen=subprocess.Popen,
        poll_interval: float = 0.05,
        timeout: float = 30.0,
    ):
        temp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or Path.home())
        self.ipc_dir = ipc_dir or temp / "renderdoc_mcp"
        self.executable_path = Path(executable_path) if executable_path else None
        self.popen = popen
        self._process = None
        self.poll_interval = poll_interval
        self.timeout = timeout

    def ensure_started(self) -> None:
        if self._process is not None:
            return
        if self.executable_path is None:
            return
        if not self.executable_path.is_file():
            raise FileNotFoundError(f"RenderDocMCP executable not found: {self.executable_path}")
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self._process = self.popen([str(self.executable_path)], **kwargs)

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        self.ensure_started()
        self.ipc_dir.mkdir(parents=True, exist_ok=True)
        request_id = str(uuid.uuid4())
        request_path = self.ipc_dir / "request.json"
        response_path = self.ipc_dir / "response.json"
        lock_path = self.ipc_dir / "lock"

        if response_path.exists():
            response_path.unlink()

        lock_path.write_text(request_id, encoding="utf-8")
        request_path.write_text(
            json.dumps({"id": request_id, "method": method, "params": params or {}}),
            encoding="utf-8",
        )
        lock_path.unlink(missing_ok=True)

        deadline = time.time() + (timeout if timeout is not None else self.timeout)
        while time.time() < deadline:
            if response_path.exists():
                raw = json.loads(response_path.read_text(encoding="utf-8"))
                response_path.unlink(missing_ok=True)
                if raw.get("id") != request_id:
                    raise RdcAutoError(f"MCP response id mismatch for {method}")
                if "error" in raw:
                    message = raw["error"].get("message", str(raw["error"]))
                    if "Method not found" in message:
                        raise McpCapabilityMissing(message)
                    raise RdcAutoError(message)
                result = raw.get("result")
                return result if isinstance(result, dict) else {"value": result}
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Timed out waiting for RenderDocMCP method {method}")

    def ping(self) -> bool:
        return self.call("ping", timeout=3.0).get("status") == "ok"
```

- [ ] **Step 4: Run MCP client tests**

Run:

```powershell
python -m pytest tests/test_mcp_client.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/mcp_client.py tests/test_mcp_client.py
git commit -m "feat: add RenderDocMCP bridge client"
```

---

### Task 8: Capture Service

**Files:**
- Create: `rdc_auto/capture.py`
- Create: `tests/test_capture_service.py`

- [ ] **Step 1: Write failing capture service tests**

Create `tests/test_capture_service.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from rdc_auto.capture import CaptureService
from rdc_auto.config import AppConfig
from rdc_auto.errors import UserActionRequired


class FakeMcp:
    def __init__(self):
        self.calls = []

    def call(self, method, params=None, timeout=None):
        self.calls.append((method, params or {}, timeout))
        if method == "launch_application":
            return {"session_id": "s1", "pid": 1234}
        if method == "get_target_status":
            return {"alive": True, "connected": True, "can_capture": True}
        if method == "trigger_capture":
            return {"rdc_path": params["output_path"], "captured": True, "pid": 1234}
        return {"status": "ok"}


class FakeMumu:
    def __init__(self, exe: Path, running: bool):
        self._exe = exe
        self._running = running
        self.terminated = False

    def executable(self):
        return self._exe

    def is_running(self):
        return self._running

    def terminate(self):
        self.terminated = True
        self._running = False


def test_attach_refuses_running_mumu_without_force(tmp_path):
    cfg = AppConfig.default()
    service = CaptureService(cfg, FakeMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=True))

    with pytest.raises(UserActionRequired):
        service.attach(force=False, confirm_vulkan=True)


def test_attach_terminates_running_mumu_with_force(tmp_path):
    cfg = AppConfig.default()
    mumu = FakeMumu(tmp_path / "MuMuNxMain.exe", running=True)
    mcp = FakeMcp()
    service = CaptureService(cfg, mcp, mumu)

    session = service.attach(force=True, confirm_vulkan=True)

    assert mumu.terminated is True
    assert session == "s1"
    assert cfg.capture.active_session_id == "s1"
    assert mcp.calls[0][0] == "launch_application"
    assert mcp.calls[0][1]["graphics_api"] == "vulkan"


def test_capture_requires_active_session(tmp_path):
    cfg = AppConfig.default()
    service = CaptureService(cfg, FakeMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    with pytest.raises(UserActionRequired):
        service.capture(tmp_path)


def test_capture_triggers_current_session(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "s1"
    service = CaptureService(cfg, FakeMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    rdc = service.capture(tmp_path)

    assert rdc.parent == tmp_path
    assert rdc.suffix == ".rdc"
    assert cfg.capture.last_rdc_path == str(rdc)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_capture_service.py -v
```

Expected: FAIL because `rdc_auto.capture` does not exist.

- [ ] **Step 3: Implement capture orchestration**

Create `rdc_auto/capture.py`:

```python
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Protocol

from .config import AppConfig
from .emulator import MuMu12
from .errors import UserActionRequired


class McpCaller(Protocol):
    def call(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        raise NotImplementedError


class CaptureService:
    def __init__(self, config: AppConfig, mcp: McpCaller, mumu: MuMu12):
        self.config = config
        self.mcp = mcp
        self.mumu = mumu

    def attach(self, force: bool = False, confirm_vulkan: bool = False) -> str:
        exe = self.mumu.executable()
        if self.mumu.is_running():
            if not force:
                raise UserActionRequired("MuMu12 is already running. Close it before attach or rerun with --force.")
            self.mumu.terminate()
        if not confirm_vulkan:
            raise UserActionRequired("Confirm MuMu12 is configured to use Vulkan before attach.")

        result = self.mcp.call(
            "launch_application",
            {
                "exe_path": str(exe),
                "working_dir": str(exe.parent),
                "cmd_line": "",
                "graphics_api": "vulkan",
            },
            timeout=120.0,
        )
        session_id = str(result["session_id"])
        self.config.capture.active_session_id = session_id
        self.config.capture.active_pid = int(result.get("pid", 0) or 0)
        return session_id

    def capture(self, output_dir: str | Path, timeout_seconds: int = 60) -> Path:
        session_id = self.config.capture.active_session_id
        if not session_id:
            raise UserActionRequired("No active RenderDoc target session. Run rdc-auto attach first.")

        status = self.mcp.call("get_target_status", {"session_id": session_id}, timeout=10.0)
        if not status.get("alive") or not status.get("connected") or not status.get("can_capture"):
            raise UserActionRequired("RenderDoc target session is not capture-capable. Run rdc-auto attach again.")

        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        output_path = directory / f"mumu12_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.rdc"
        result = self.mcp.call(
            "trigger_capture",
            {
                "session_id": session_id,
                "output_path": str(output_path),
                "timeout_seconds": timeout_seconds,
            },
            timeout=timeout_seconds + 30.0,
        )
        rdc_path = Path(result.get("rdc_path") or output_path)
        self.config.capture.last_output_dir = str(directory)
        self.config.capture.last_rdc_path = str(rdc_path)
        return rdc_path

    def close(self, terminate_process: bool = False) -> None:
        session_id = self.config.capture.active_session_id
        if not session_id:
            return
        self.mcp.call(
            "close_target",
            {"session_id": session_id, "terminate_process": terminate_process},
            timeout=10.0,
        )
        self.config.capture.active_session_id = None
        self.config.capture.active_pid = None
```

- [ ] **Step 4: Run capture tests**

Run:

```powershell
python -m pytest tests/test_capture_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/capture.py tests/test_capture_service.py
git commit -m "feat: add attach and capture orchestration"
```

---

### Task 9: Mesh JSON to OBJ/MTL Conversion

**Files:**
- Create: `rdc_auto/mesh_convert.py`
- Create: `tests/test_mesh_convert.py`

- [ ] **Step 1: Write failing mesh conversion tests**

Create `tests/test_mesh_convert.py`:

```python
from __future__ import annotations

import json

from rdc_auto.mesh_convert import convert_mesh_json_to_obj


def test_convert_mesh_json_to_obj_and_mtl(tmp_path):
    source = tmp_path / "mesh.json"
    source.write_text(
        json.dumps(
            {
                "indices": [0, 1, 2],
                "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "normal": [[0, 0, 1], [0, 0, 1], [0, 0, 1]],
                "uv0": [[0, 0], [1, 0], [0, 1]],
            }
        ),
        encoding="utf-8",
    )
    obj = tmp_path / "mesh.obj"
    mtl = tmp_path / "mesh.mtl"

    convert_mesh_json_to_obj(source, obj, mtl, material_name="mat_001")

    obj_text = obj.read_text(encoding="utf-8")
    mtl_text = mtl.read_text(encoding="utf-8")
    assert "mtllib mesh.mtl" in obj_text
    assert "usemtl mat_001" in obj_text
    assert "v 1 0 0" in obj_text
    assert "vn 0 0 1" in obj_text
    assert "vt 1 0" in obj_text
    assert "f 1/1/1 2/2/2 3/3/3" in obj_text
    assert "newmtl mat_001" in mtl_text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_mesh_convert.py -v
```

Expected: FAIL because `rdc_auto.mesh_convert` does not exist.

- [ ] **Step 3: Implement OBJ/MTL converter**

Create `rdc_auto/mesh_convert.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def _fmt(values: Iterable[float]) -> str:
    return " ".join(f"{float(value):g}" for value in values)


def convert_mesh_json_to_obj(
    source_json: str | Path,
    obj_path: str | Path,
    mtl_path: str | Path,
    material_name: str,
) -> None:
    source_json = Path(source_json)
    obj_path = Path(obj_path)
    mtl_path = Path(mtl_path)
    data = json.loads(source_json.read_text(encoding="utf-8"))

    positions = data.get("position") or data.get("positions") or []
    normals = data.get("normal") or data.get("normals") or []
    uvs = data.get("uv0") or data.get("uv") or []
    indices = data.get("indices") or []

    obj_path.parent.mkdir(parents=True, exist_ok=True)
    mtl_path.parent.mkdir(parents=True, exist_ok=True)

    with mtl_path.open("w", encoding="utf-8", newline="\n") as mtl:
        mtl.write(f"newmtl {material_name}\n")
        mtl.write("Kd 0.8 0.8 0.8\n")
        mtl.write("Ka 0.0 0.0 0.0\n")
        mtl.write("Ks 0.0 0.0 0.0\n")

    with obj_path.open("w", encoding="utf-8", newline="\n") as obj:
        obj.write(f"mtllib {mtl_path.name}\n")
        obj.write(f"usemtl {material_name}\n")
        for pos in positions:
            obj.write(f"v {_fmt(pos[:3])}\n")
        for uv in uvs:
            obj.write(f"vt {_fmt(uv[:2])}\n")
        for normal in normals:
            obj.write(f"vn {_fmt(normal[:3])}\n")

        for offset in range(0, len(indices), 3):
            tri = indices[offset : offset + 3]
            if len(tri) != 3:
                continue
            face = []
            for raw_index in tri:
                idx = int(raw_index) + 1
                vt = idx if uvs else ""
                vn = idx if normals else ""
                if uvs and normals:
                    face.append(f"{idx}/{vt}/{vn}")
                elif uvs:
                    face.append(f"{idx}/{vt}")
                elif normals:
                    face.append(f"{idx}//{vn}")
                else:
                    face.append(str(idx))
            obj.write("f " + " ".join(face) + "\n")
```

- [ ] **Step 4: Run mesh conversion tests**

Run:

```powershell
python -m pytest tests/test_mesh_convert.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/mesh_convert.py tests/test_mesh_convert.py
git commit -m "feat: convert MCP mesh JSON to OBJ"
```

---

### Task 10: Asset Export Service

**Files:**
- Create: `rdc_auto/export_assets.py`
- Create: `tests/test_export_assets.py`

- [ ] **Step 1: Write failing export tests**

Create `tests/test_export_assets.py`:

```python
from __future__ import annotations

import json

from rdc_auto.export_assets import ExportService


class FakeMcp:
    def __init__(self):
        self.calls = []

    def call(self, method, params=None, timeout=None):
        params = params or {}
        self.calls.append((method, params, timeout))
        if method == "open_capture":
            return {"success": True}
        if method == "get_textures":
            return {"textures": [{"resource_id": "101", "name": "Albedo"}]}
        if method == "export_texture_to_file":
            return {"output_path": params["output_path"]}
        if method == "get_draw_calls":
            return {"draws": [{"event_id": 12, "name": "Character"}]}
        if method == "export_mesh_to_file":
            with open(params["output_path"], "w", encoding="utf-8") as handle:
                json.dump({"indices": [0, 1, 2], "position": [[0, 0, 0], [1, 0, 0], [0, 1, 0]]}, handle)
            return {"output_path": params["output_path"]}
        return {}


def test_export_textures_and_meshes(tmp_path):
    rdc = tmp_path / "capture.rdc"
    rdc.write_text("", encoding="utf-8")
    service = ExportService(FakeMcp())

    manifest = service.export(rdc, tmp_path / "out", assets="both")

    assert manifest["assets"]["textures"]["success"] == 1
    assert manifest["assets"]["meshes"]["success"] == 1
    texture_call = [call for call in service.mcp.calls if call[0] == "export_texture_to_file"][0]
    assert texture_call[1]["output_path"] == str(tmp_path / "out" / "textures" / "Albedo_101.png")
    assert (tmp_path / "out" / "meshes" / "12_Character.obj").is_file()
    assert (tmp_path / "out" / "manifest.json").is_file()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_export_assets.py -v
```

Expected: FAIL because `rdc_auto.export_assets` does not exist.

- [ ] **Step 3: Implement export service**

Create `rdc_auto/export_assets.py`:

```python
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Protocol

from .mesh_convert import convert_mesh_json_to_obj


class McpCaller(Protocol):
    def call(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        raise NotImplementedError


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("_") or "unnamed"


class ExportService:
    def __init__(self, mcp: McpCaller):
        self.mcp = mcp

    def export(self, rdc_path: str | Path, output_dir: str | Path, assets: str) -> dict:
        rdc_path = Path(rdc_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "source_rdc": str(rdc_path),
            "exported_at": dt.datetime.now().astimezone().isoformat(),
            "assets": {
                "textures": {"success": 0, "failed": 0},
                "meshes": {"success": 0, "failed": 0},
            },
            "failures": [],
        }

        self.mcp.call("open_capture", {"capture_path": str(rdc_path)}, timeout=120.0)

        if assets in {"textures", "both"}:
            self._export_textures(output_dir, manifest)
        if assets in {"meshes", "both"}:
            self._export_meshes(output_dir, manifest)

        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def _export_textures(self, output_dir: Path, manifest: dict) -> None:
        textures_dir = output_dir / "textures"
        textures_dir.mkdir(parents=True, exist_ok=True)
        textures = self.mcp.call("get_textures", timeout=60.0).get("textures", [])
        for texture in textures:
            resource_id = str(texture.get("resource_id") or texture.get("id") or "")
            name = safe_name(str(texture.get("name") or "texture"))
            path = textures_dir / f"{name}_{resource_id}.png"
            try:
                self.mcp.call(
                    "export_texture_to_file",
                    {"resource_id": resource_id, "output_path": str(path), "file_type": "PNG"},
                    timeout=120.0,
                )
                manifest["assets"]["textures"]["success"] += 1
            except Exception as exc:
                manifest["assets"]["textures"]["failed"] += 1
                manifest["failures"].append({"type": "texture", "resource_id": resource_id, "error": str(exc)})

    def _export_meshes(self, output_dir: Path, manifest: dict) -> None:
        meshes_dir = output_dir / "meshes"
        raw_dir = output_dir / "raw_mesh_json"
        meshes_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        draws = self.mcp.call("get_draw_calls", {"include_children": True, "only_actions": True}, timeout=60.0).get("draws", [])
        for draw in draws:
            event_id = int(draw.get("event_id") or draw.get("eventId") or 0)
            if event_id <= 0:
                continue
            name = safe_name(str(draw.get("name") or f"draw_{event_id}"))
            stem = f"{event_id}_{name}"
            raw_json = raw_dir / f"{stem}.json"
            obj = meshes_dir / f"{stem}.obj"
            mtl = meshes_dir / f"{stem}.mtl"
            try:
                self.mcp.call(
                    "export_mesh_to_file",
                    {"event_id": event_id, "output_path": str(raw_json)},
                    timeout=120.0,
                )
                convert_mesh_json_to_obj(raw_json, obj, mtl, material_name=f"mat_{event_id}")
                manifest["assets"]["meshes"]["success"] += 1
            except Exception as exc:
                manifest["assets"]["meshes"]["failed"] += 1
                manifest["failures"].append({"type": "mesh", "event_id": event_id, "error": str(exc)})
```

- [ ] **Step 4: Run export tests**

Run:

```powershell
python -m pytest tests/test_export_assets.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/export_assets.py tests/test_export_assets.py
git commit -m "feat: add RDC asset export service"
```

---

### Task 11: CLI Wiring

**Files:**
- Modify: `rdc_auto/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_cli.py`:

```python
from rdc_auto.cli import build_parser


def test_parser_accepts_short_commands():
    parser = build_parser()

    assert parser.parse_args(["setup"]).command == "setup"
    assert parser.parse_args(["attach"]).command == "attach"
    assert parser.parse_args(["capture"]).command == "capture"
    assert parser.parse_args(["export"]).command == "export"


def test_capture_parser_accepts_out():
    parser = build_parser()
    args = parser.parse_args(["capture", "--out", "D:\\Captures"])

    assert args.out == "D:\\Captures"


def test_export_parser_accepts_assets_and_out():
    parser = build_parser()
    args = parser.parse_args(["export", "D:\\a.rdc", "--assets", "textures", "--out", "D:\\Exports"])

    assert args.rdc_path == "D:\\a.rdc"
    assert args.assets == "textures"
    assert args.out == "D:\\Exports"
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `build_parser` is missing.

- [ ] **Step 3: Implement CLI parser and command handlers**

Replace `rdc_auto/cli.py` with:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .capture import CaptureService
from .config import load_config, save_config
from .emulator import MuMu12
from .errors import RdcAutoError, UserActionRequired
from .export_assets import ExportService
from .log_setup import configure_logging
from .mcp_client import FileIpcMcpClient
from .mcp_installer import McpInstaller
from .paths import find_renderdoc_install, validate_mumu_root
from .prompts import choose_option, prompt_path
from .renderdoc_installer import RenderDocInstaller


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rdc-auto")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup")

    attach = sub.add_parser("attach")
    attach.add_argument("--force", action="store_true")
    attach.add_argument("--yes-vulkan", action="store_true")

    capture = sub.add_parser("capture")
    capture.add_argument("--out")
    capture.add_argument("--timeout", type=int, default=60)

    export = sub.add_parser("export")
    export.add_argument("rdc_path", nargs="?")
    export.add_argument("--assets", choices=["textures", "meshes", "both"])
    export.add_argument("--out")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose)
    cfg = load_config()
    try:
        if args.command == "setup":
            _cmd_setup(cfg)
        elif args.command == "attach":
            _cmd_attach(cfg, force=args.force, yes_vulkan=args.yes_vulkan)
        elif args.command == "capture":
            _cmd_capture(cfg, args)
        elif args.command == "export":
            _cmd_export(cfg, args)
        save_config(cfg)
        return 0
    except UserActionRequired as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RdcAutoError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


def _cmd_setup(cfg) -> None:
    installer = RenderDocInstaller(cfg)
    if not installer.ensure_installed():
        url = installer.resolve_download_url()
        installer_path = installer.download_installer(url)
        installer.run_installer(installer_path)
        found = find_renderdoc_install()
        cfg.renderdoc.install_dir = found.get("install_dir", "")
        cfg.renderdoc.qrenderdoc_path = found.get("qrenderdoc_path", "")
        cfg.renderdoc.renderdoccmd_path = found.get("renderdoccmd_path", "")

    if not cfg.emulator.root_dir:
        cfg.emulator.root_dir = str(prompt_path("MuMu12 root directory"))
    validate_mumu_root(cfg.emulator.root_dir)

    mcp = McpInstaller(cfg)
    mcp_exe = mcp.ensure_installed()
    cfg.mcp.executable_path = str(mcp_exe)
    print("setup complete")


def _cmd_attach(cfg, force: bool, yes_vulkan: bool) -> None:
    if not cfg.emulator.root_dir:
        cfg.emulator.root_dir = str(prompt_path("MuMu12 root directory"))
    if not yes_vulkan:
        answer = choose_option("Confirm MuMu12 graphics API", ["vulkan", "stop"], default="vulkan")
        if answer != "vulkan":
            raise UserActionRequired("Set MuMu12 graphics API to Vulkan before attach.")
    service = CaptureService(cfg, _mcp_client(cfg), MuMu12(cfg))
    session_id = service.attach(force=force, confirm_vulkan=True)
    print(f"attached session: {session_id}")


def _cmd_capture(cfg, args) -> None:
    out = Path(args.out) if args.out else prompt_path("Capture output directory", cfg.capture.last_output_dir or None)
    service = CaptureService(cfg, _mcp_client(cfg), MuMu12(cfg))
    rdc_path = service.capture(out, timeout_seconds=args.timeout)
    print(f"captured: {rdc_path}")


def _cmd_export(cfg, args) -> None:
    rdc_path = Path(args.rdc_path) if args.rdc_path else prompt_path("RDC file", cfg.capture.last_rdc_path or None)
    assets = args.assets or choose_option("Export assets", ["textures", "meshes", "both"], default="both")
    out = Path(args.out) if args.out else prompt_path("Export output directory")
    manifest = ExportService(_mcp_client(cfg)).export(rdc_path, out, assets)
    print(f"export complete: {out}")
    print(f"textures: {manifest['assets']['textures']['success']} ok, {manifest['assets']['textures']['failed']} failed")
    print(f"meshes: {manifest['assets']['meshes']['success']} ok, {manifest['assets']['meshes']['failed']} failed")


def _mcp_client(cfg) -> FileIpcMcpClient:
    if not cfg.mcp.executable_path:
        cfg.mcp.executable_path = str(McpInstaller(cfg).ensure_installed())
    return FileIpcMcpClient(executable_path=cfg.mcp.executable_path)
```

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Run all Python tests**

Run:

```powershell
python -m pytest -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add rdc_auto/cli.py tests/test_cli.py
git commit -m "feat: wire rdc-auto CLI commands"
```

---

### Task 12: Codex Skill Source

**Files:**
- Create: `skills/rdc-auto/SKILL.md`
- Create: `skills/rdc-auto/agents/openai.yaml`

- [ ] **Step 1: Create the Skill file**

Create `skills/rdc-auto/SKILL.md`:

```markdown
---
name: rdc-auto
description: Use when the user wants to install or operate the rdc-auto RenderDoc automation workflow for MuMu12, including setting up RenderDoc v1.44, RenderDocMCP, launching MuMu12 through RenderDoc, capturing the current emulator frame, or exporting textures and meshes from .rdc files.
---

# rdc-auto

Use this Skill to drive the `rdc-auto` CLI. Keep the Skill thin: ask for missing paths or asset choices, then run the CLI.

## Commands

- Environment setup: `rdc-auto setup`
- Start MuMu12 through RenderDoc: `rdc-auto attach`
- Capture current emulator frame: `rdc-auto capture`
- Export assets from an RDC: `rdc-auto export`

## Workflow

1. If the user asks to deploy or install the capture environment, run `rdc-auto setup`.
2. If the user asks to attach or start the emulator capture environment, run `rdc-auto attach`.
3. If MuMu12 is already running, tell the user to close it. Use `rdc-auto attach --force` only after the user explicitly approves automatic termination.
4. If the user asks to capture the current emulator frame, run `rdc-auto capture`.
5. If capture output path is missing, ask for a save directory.
6. If the user asks to analyze, export, extract textures, or extract models from an `.rdc`, run `rdc-auto export`.
7. If export inputs are missing, ask for the `.rdc` path, asset type (`textures`, `meshes`, or `both`), and output directory.

## Fixed Constraints

- RenderDoc version is v1.44.
- RenderDoc installer is downloaded from `https://renderdoc.org/builds` when RenderDoc is missing.
- RenderDocMCP is installed from the latest GitHub release setup executable at `https://api.github.com/repos/Smilexs/RenderDocMCP/releases/latest`.
- The only supported emulator in the first release is MuMu12.
- MuMu12 executable path is `<MuMu12Root>\MuMuPlayer-12.0\nx_main\MuMuNxMain.exe`.
- MuMu12 must use Vulkan.

## Error Handling

- RenderDoc missing: run `rdc-auto setup`.
- RenderDocMCP bridge unavailable: run `rdc-auto setup` and ask the user to restart RenderDoc if needed.
- MuMu12 root invalid: ask for the MuMu12 root installation directory.
- MuMu12 already running: ask the user to close it before attach.
- Vulkan not confirmed: ask the user to switch MuMu12 to Vulkan.
- Capture session expired: run `rdc-auto attach` again.
- Export failures: report the manifest path and summarize failed textures or meshes.
```

- [ ] **Step 2: Create OpenAI Skill metadata**

Create `skills/rdc-auto/agents/openai.yaml`:

```yaml
display_name: rdc-auto
short_description: Automate RenderDoc v1.44 capture and asset export for MuMu12.
default_prompt: Set up RenderDoc capture, launch MuMu12 through RenderDoc, capture a frame, or export textures and meshes from an RDC file.
```

- [ ] **Step 3: Validate Skill file frontmatter**

Run:

```powershell
python - <<'PY'
from pathlib import Path
text = Path("skills/rdc-auto/SKILL.md").read_text(encoding="utf-8")
assert text.startswith("---\n")
assert "name: rdc-auto" in text
assert "description:" in text
print("skill metadata ok")
PY
```

Expected: `skill metadata ok`.

- [ ] **Step 4: Commit**

```powershell
git add skills/rdc-auto
git commit -m "feat: add rdc-auto Codex skill"
```

---

### Task 13: Bootstrap and Packaging Scripts

**Files:**
- Create: `scripts/bootstrap.ps1`
- Create: `scripts/build_exe.ps1`

- [ ] **Step 1: Create developer bootstrap script**

Create `scripts/bootstrap.ps1`:

```powershell
$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python was not found. Install Python 3.11+ for source development, or use the packaged rdc-auto.exe."
}

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -v
```

- [ ] **Step 2: Create PyInstaller build script**

Create `scripts/build_exe.ps1`:

```powershell
$ErrorActionPreference = "Stop"

python -m pip install -e ".[dev]"
python -m pytest -v
python -m PyInstaller --onefile --name rdc-auto --console rdc_auto\__main__.py

$exe = Join-Path $PWD "dist\rdc-auto.exe"
if (-not (Test-Path $exe)) {
  throw "Expected executable was not produced: $exe"
}

Write-Host "Built $exe"
```

- [ ] **Step 3: Run bootstrap**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

Expected: dependencies install and all tests PASS.

- [ ] **Step 4: Run executable build**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
```

Expected: `dist\rdc-auto.exe` exists.

- [ ] **Step 5: Commit**

```powershell
git add scripts/bootstrap.ps1 scripts/build_exe.ps1
git commit -m "build: add bootstrap and executable packaging scripts"
```

---

### Task 14: Manual Acceptance Checklist

**Files:**
- Create: `docs/manual-acceptance.md`

- [ ] **Step 1: Create manual acceptance document**

Create `docs/manual-acceptance.md`:

```markdown
# rdc-auto Manual Acceptance

Run these checks on a Windows machine with MuMu12 installed.

## Setup

1. Run `rdc-auto setup`.
2. Confirm RenderDoc v1.44 is detected or installed.
3. Confirm RenderDocMCP setup exe is downloaded from the latest GitHub release.
4. Confirm RenderDocMCP is installed and `config.json` records the installed executable path.
5. Enter the MuMu12 root directory when prompted.
6. Confirm `<MuMu12Root>\MuMuPlayer-12.0\nx_main\MuMuNxMain.exe` exists.

## Attach

1. Close MuMu12 if it is running.
2. Set MuMu12 graphics API to Vulkan.
3. Run `rdc-auto attach`.
4. Confirm MuMu12 launches through RenderDoc.
5. Confirm the CLI prints an active session id.

## Capture

1. Navigate manually to the desired game scene.
2. Run `rdc-auto capture`.
3. Choose an output directory.
4. Confirm a `.rdc` file is written.

## Export

1. Run `rdc-auto export`.
2. Use the captured `.rdc`.
3. Select `both`.
4. Choose an output directory.
5. Confirm `textures`, `meshes`, `raw_mesh_json`, and `manifest.json` are written.
6. Confirm PNG files are readable.
7. Confirm OBJ/MTL files import into a DCC or viewer.
```

- [ ] **Step 2: Commit**

```powershell
git add docs/manual-acceptance.md
git commit -m "docs: add rdc-auto manual acceptance checklist"
```

---

## Final Verification

- [ ] Run the full test suite:

```powershell
python -m pytest -v
```

Expected: all tests PASS.

- [ ] Build the executable:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
```

Expected: `dist\rdc-auto.exe` exists.

- [ ] Check git status:

```powershell
git status --short
```

Expected: no uncommitted source, test, Skill, or docs changes.

## Self-Review

Spec coverage:

- RenderDoc v1.44 setup: Task 5 and Task 11.
- RenderDocMCP release exe install: Task 6 and Task 11.
- Installed RenderDocMCP executable startup: Task 7 and Task 11.
- MuMu12 root and fixed executable path: Task 4 and Task 11.
- MuMu12 Vulkan prompt: Task 8 and Task 11.
- RenderDoc-launched MuMu12 session: Task 8.
- Current-frame capture: Task 8.
- Texture PNG export: Task 10.
- Mesh OBJ/MTL export: Task 9 and Task 10.
- Codex Skill named `rdc-auto`: Task 12.
- Packaging and acceptance: Task 13 and Task 14.

Incomplete-marker scan:

- No incomplete markers are intentionally used in this plan.
- Every task includes file paths, concrete test commands, expected outcomes, and commit commands.

Type consistency:

- The session methods are consistently named `launch_application`, `get_target_status`, `trigger_capture`, and `close_target`.
- Asset selection values are consistently `textures`, `meshes`, and `both`.
- MuMu12 executable resolution consistently uses `MuMuPlayer-12.0\nx_main\MuMuNxMain.exe`.
