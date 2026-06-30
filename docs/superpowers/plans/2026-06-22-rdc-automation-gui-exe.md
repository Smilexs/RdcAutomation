# RdcAutomation GUI EXE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop GUI executable from `html-ui-prototype/index.html`, wiring the existing `rdc-auto` setup, attach, capture, and export workflow behind the prototype UI.

**Architecture:** Keep the prototype as the first-class visual surface and run it inside a lightweight Python desktop shell. JavaScript calls a Python bridge exposed by pywebview; the bridge delegates long-running work to a job manager and reuses existing `rdc_auto` services instead of shelling out to `rdc-auto.exe`. AI assistant behavior in the first GUI release is limited to saved UI settings and deterministic local replies.

**Tech Stack:** Python 3.11+, pywebview 6.x, stdlib threading/queue/json/subprocess/pathlib, existing `rdc_auto` modules, pytest, PyInstaller, PowerShell build scripts.

---

## Repository Root

All paths are relative to:

```text
E:\ZSGame\AIProjects\RdcAutomation
```

## Prototype Coverage

The source prototype is:

```text
html-ui-prototype/index.html
```

The GUI must preserve these visible areas and workflows:

- Sidebar pages: 工作台, 环境设置, 捕捉 RDC, 资源导出, AI 助手, 日志与配置.
- Top status row: RenderDoc, MuMu12, session, MCP, refresh action.
- Environment page: RenderDoc path, MuMu12 root, VM index, Vulkan confirmation, RenderDoc MCP executable path.
- Capture page: attach mode, force-close confirmation, capture output directory, timeout, release session.
- Export page: MCP status controls, normal export, EID export, recent RDC handoff.
- AI page: provider/model/base URL/key controls and chat UI, with no external LLM call in the first release.
- Logs page: config preview, log controls, reset, simulated error action.
- Toasts, progress bars, bottom log, confirmation modal, tab switching, and responsive layout.

## Scope Decisions

- Ship a new GUI executable named `RdcAutomation.exe`; keep the existing console executable `rdc-auto.exe`.
- The GUI calls Python functions directly through pywebview. Do not make the browser execute local commands.
- Use the existing Python services for real work: `RenderDocInstaller`, `McpInstaller`, `CaptureService`, `ExportService`, `CaptureBridgeClient`, and `FileIpcMcpClient`.
- Extract reusable CLI workflow code into `rdc_auto/operations.py` so the CLI and GUI share the same behavior.
- Long-running actions run through a background job manager. The UI polls job state and updates progress/logs.
- AI assistant first release stores provider/model/base URL UI state and returns local rule-based diagnostic messages. It does not send API keys or prompts to any network endpoint.
- EID model export is real by calling existing MCP mesh export by event id. EID bound-texture export returns a clear unsupported-capability error if the installed MCP bridge does not expose a bound-texture method.

## File Structure

Create and modify this structure:

```text
pyproject.toml
README.md
rdc_auto/
  cli.py
  config.py
  operations.py
  processes.py
  export_assets.py
  gui/
    __init__.py
    __main__.py
    app.py
    bridge.py
    jobs.py
    paths.py
    status.py
    static/
      index.html
scripts/
  build_gui_exe.ps1
tests/
  test_cli.py
  test_config.py
  test_export_assets.py
  test_gui_bridge.py
  test_gui_jobs.py
  test_gui_static.py
  test_operations.py
  test_processes.py
docs/
  gui-manual-acceptance.md
```

Responsibility boundaries:

- `rdc_auto/operations.py`: public programmatic operations shared by CLI and GUI.
- `rdc_auto/processes.py`: reusable Windows process helpers currently embedded in `cli.py`.
- `rdc_auto/gui/app.py`: pywebview window startup only.
- `rdc_auto/gui/bridge.py`: JavaScript-facing API methods and response envelope.
- `rdc_auto/gui/jobs.py`: background job execution, progress, logs, cancellation state.
- `rdc_auto/gui/status.py`: current status snapshot and config preview.
- `rdc_auto/gui/paths.py`: packaged static file resolution for source and PyInstaller modes.
- `rdc_auto/gui/static/index.html`: packaged copy of the prototype with bridge integration.

## API Contract

All Python bridge methods return JSON-serializable dictionaries.

Successful response:

```python
{
    "ok": True,
    "data": {"key": "value"},
    "logs": ["human readable log line"],
}
```

Failure response:

```python
{
    "ok": False,
    "error": {
        "type": "UserActionRequired",
        "message": "MuMu12 is already running. Close it before attach or enable force close.",
        "action_required": True,
    },
    "logs": ["attach blocked"],
}
```

Long-running job response:

```python
{
    "job_id": "01HXEXAMPLE",
    "action": "capture",
    "state": "running",
    "progress": 40,
    "logs": ["starting capture"],
    "result": None,
    "error": None,
}
```

---

### Task 1: GUI Dependency and Static Asset Scaffold

**Files:**
- Modify: `pyproject.toml`
- Create: `rdc_auto/gui/__init__.py`
- Create: `rdc_auto/gui/paths.py`
- Create: `rdc_auto/gui/static/index.html`
- Create: `tests/test_gui_static.py`

- [ ] **Step 1: Write the failing static asset test**

Create `tests/test_gui_static.py`:

```python
from __future__ import annotations

from pathlib import Path

from rdc_auto.gui.paths import gui_static_dir, gui_index_path


def test_gui_index_is_packaged():
    index = gui_index_path()

    assert index == gui_static_dir() / "index.html"
    assert index.is_file()
    html = index.read_text(encoding="utf-8")
    assert "RdcAutomation" in html
    assert 'data-view-target="dashboard"' in html
    assert 'data-action="capture"' in html
    assert "window.pywebview" in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest tests/test_gui_static.py -v
```

Expected: FAIL because `rdc_auto.gui` does not exist.

- [ ] **Step 3: Add GUI dependency group**

Modify `pyproject.toml` optional dependencies:

```toml
[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pyinstaller>=6.0"
]
gui = [
  "pywebview>=6,<7"
]
```

Do not remove the existing `dev` dependencies.

- [ ] **Step 4: Create static path helpers**

Create `rdc_auto/gui/__init__.py`:

```python
from __future__ import annotations
```

Create `rdc_auto/gui/paths.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


def package_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        return Path(bundle_root)
    return Path(__file__).resolve().parents[2]


def gui_static_dir() -> Path:
    bundled = package_root() / "rdc_auto" / "gui" / "static"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parent / "static"


def gui_index_path() -> Path:
    return gui_static_dir() / "index.html"
```

- [ ] **Step 5: Copy the prototype into package assets**

Run:

```powershell
New-Item -ItemType Directory -Force rdc_auto\gui\static
Copy-Item -LiteralPath html-ui-prototype\index.html -Destination rdc_auto\gui\static\index.html
```

Then edit `rdc_auto/gui/static/index.html` and add this script block before the existing inline prototype script:

```html
  <script>
    window.RdcBackend = {
      available() {
        return Boolean(window.pywebview && window.pywebview.api);
      },
      call(method, payload) {
        if (!this.available()) {
          return Promise.resolve({ ok: false, error: { type: "BackendUnavailable", message: "GUI backend is not attached.", action_required: false }, logs: [] });
        }
        return window.pywebview.api[method](payload || {});
      }
    };
  </script>
```

- [ ] **Step 6: Run the static asset test**

Run:

```powershell
python -m pytest tests/test_gui_static.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml rdc_auto/gui tests/test_gui_static.py
git commit -m "feat: add GUI static asset scaffold"
```

---

### Task 2: Process Helpers and Shared Operations

**Files:**
- Create: `rdc_auto/processes.py`
- Create: `rdc_auto/operations.py`
- Modify: `rdc_auto/config.py`
- Modify: `rdc_auto/cli.py`
- Create: `tests/test_processes.py`
- Create: `tests/test_operations.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing process helper tests**

Create `tests/test_processes.py`:

```python
from __future__ import annotations

import subprocess

from rdc_auto.processes import count_processes, is_process_running, tasklist_count_from_csv


def test_tasklist_count_from_csv_counts_matching_rows():
    stdout = '"Image Name","PID"\n"qrenderdoc.exe","10"\n"notepad.exe","11"\n"qrenderdoc.exe","12"\n'

    assert tasklist_count_from_csv(stdout, "qrenderdoc.exe") == 2


def test_is_process_running_uses_runner():
    def runner(args, capture_output, text, check):
        return subprocess.CompletedProcess(args, 0, stdout='"Image Name","PID"\n"RenderDocMCP.exe","20"\n')

    assert count_processes("RenderDocMCP.exe", runner=runner) == 1
    assert is_process_running("RenderDocMCP.exe", runner=runner) is True
```

- [ ] **Step 2: Run process tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_processes.py -v
```

Expected: FAIL because `rdc_auto.processes` does not exist.

- [ ] **Step 3: Implement process helpers**

Create `rdc_auto/processes.py`:

```python
from __future__ import annotations

import csv
import subprocess
from io import StringIO
from pathlib import Path
from typing import Callable

from .errors import RdcAutoError


Runner = Callable[..., subprocess.CompletedProcess[str]]


def tasklist_count_from_csv(stdout: str, image_name: str) -> int:
    target = image_name.lower()
    count = 0
    for row in csv.reader(StringIO(stdout)):
        if row and row[0].strip().lower() == target:
            count += 1
    return count


def count_processes(image_name: str, runner: Runner = subprocess.run) -> int:
    try:
        result = runner(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 0
    return tasklist_count_from_csv(result.stdout, image_name)


def is_process_running(image_name: str, runner: Runner = subprocess.run) -> bool:
    return count_processes(image_name, runner=runner) > 0


def terminate_process_tree(image_name: str, runner: Runner = subprocess.run) -> None:
    try:
        result = runner(["taskkill", "/IM", image_name, "/T", "/F"], capture_output=True, text=True, check=False)
    except OSError:
        return
    if result.returncode != 0 and count_processes(image_name, runner=runner) > 0:
        details = "\n".join(part for part in [result.stderr, result.stdout] if part).strip()
        raise RdcAutoError(f"Failed to stop process {image_name}: {details}")


def executable_name(path: str | Path) -> str:
    return Path(path).name
```

- [ ] **Step 4: Write failing shared operation tests**

Create `tests/test_operations.py`:

```python
from __future__ import annotations

from pathlib import Path

from rdc_auto.config import AppConfig
from rdc_auto.operations import OperationContext, release_session


def test_release_session_clears_capture_state(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "session-1"
    cfg.capture.active_launch_id = "launch-1"
    cfg.capture.active_pid = 123
    cfg.capture.active_session_started_at = "2026-06-22T00:00:00+08:00"

    release_session(OperationContext(config=cfg))

    assert cfg.capture.active_session_id is None
    assert cfg.capture.active_launch_id == ""
    assert cfg.capture.active_pid is None
    assert cfg.capture.active_session_started_at is None


def test_operation_context_uses_existing_config():
    cfg = AppConfig.default()
    ctx = OperationContext(config=cfg)

    assert ctx.config is cfg
    assert Path(ctx.config.mcp.install_dir).name == "mcp"
```

- [ ] **Step 5: Run operation tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_operations.py -v
```

Expected: FAIL because `rdc_auto.operations` does not exist.

- [ ] **Step 6: Add launch tracking and create shared operations module**

Modify `rdc_auto/config.py` and add `active_launch_id` to `CaptureConfig`:

```python
active_launch_id: str = ""
```

Create `rdc_auto/operations.py`:

```python
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .capture import CaptureService
from .capture_bridge import CaptureBridgeClient, CaptureBridgeInstaller
from .config import AppConfig, load_config, save_config
from .emulator import MuMu12
from .errors import DependencyMissing, McpCapabilityMissing, RdcAutoError, UserActionRequired
from .export_assets import ExportService
from .mcp_client import FileIpcMcpClient
from .mcp_installer import McpInstaller
from .mcp_patch import patch_renderdoc_mcp_extension
from .paths import canonical_mumu_root, validate_mumu_root
from .processes import count_processes, is_process_running, terminate_process_tree
from .renderdoc_installer import RenderDocInstaller


Progress = Callable[[str, int], None]


@dataclass
class OperationContext:
    config: AppConfig | None = None
    progress: Progress | None = None

    def cfg(self) -> AppConfig:
        if self.config is None:
            self.config = load_config()
        return self.config

    def emit(self, message: str, progress: int) -> None:
        if self.progress is not None:
            self.progress(message, progress)


def setup_environment(ctx: OperationContext) -> dict:
    cfg = ctx.cfg()
    ctx.emit("checking RenderDoc", 5)
    installer = RenderDocInstaller(cfg)
    if not installer.ensure_installed():
        url = installer.resolve_download_url()
        ctx.emit("downloading RenderDoc installer", 15)
        installer_path = installer.download_installer(url)
        ctx.emit("running RenderDoc installer", 30)
        installer.run_installer(installer_path)
        if not installer.ensure_installed():
            raise DependencyMissing("RenderDoc v1.44 installation completed, but qrenderdoc.exe with version 1.44 was not found.")

    ctx.emit("validating MuMu12", 45)
    if cfg.emulator.root_dir:
        root = canonical_mumu_root(cfg.emulator.root_dir, cfg.emulator.exe_relative_path)
        cfg.emulator.root_dir = str(root)
        validate_mumu_root(root, cfg.emulator.exe_relative_path)

    ctx.emit("installing RenderDocMCP", 65)
    mcp_exe = McpInstaller(cfg).ensure_installed()
    cfg.mcp.executable_path = str(mcp_exe)
    save_config(cfg)
    ctx.emit("environment setup complete", 100)
    return {"renderdoc_path": cfg.renderdoc.qrenderdoc_path, "mcp_path": cfg.mcp.executable_path}


def check_environment(ctx: OperationContext) -> dict:
    cfg = ctx.cfg()
    ctx.emit("checking RenderDoc", 20)
    renderdoc_ready = RenderDocInstaller(cfg).ensure_installed()
    ctx.emit("checking MuMu12", 45)
    mumu_ready = False
    if cfg.emulator.root_dir:
        try:
            cfg.emulator.root_dir = str(canonical_mumu_root(cfg.emulator.root_dir, cfg.emulator.exe_relative_path))
            validate_mumu_root(cfg.emulator.root_dir, cfg.emulator.exe_relative_path)
            mumu_ready = True
        except FileNotFoundError:
            mumu_ready = False
    ctx.emit("checking RenderDocMCP", 70)
    mcp_path = McpInstaller(cfg).discover_executable(allow_configured=True)
    save_config(cfg)
    ctx.emit("environment check complete", 100)
    return {
        "renderdoc_ready": renderdoc_ready,
        "mumu_ready": mumu_ready,
        "mcp_ready": bool(mcp_path),
        "renderdoc_path": cfg.renderdoc.qrenderdoc_path,
        "mcp_path": str(mcp_path) if mcp_path else "",
    }


def attach(ctx: OperationContext, force: bool, confirm_vulkan: bool, vm_index: str = "") -> dict:
    cfg = ctx.cfg()
    if vm_index:
        cfg.emulator.vm_index = vm_index
    ctx.emit("starting RenderDoc capture bridge", 10)
    service = CaptureService(cfg, capture_bridge_client(cfg, start_qrenderdoc=True), MuMu12(cfg))
    launch_id = service.attach(force=force, confirm_vulkan=confirm_vulkan)
    cfg.capture.active_launch_id = launch_id
    save_config(cfg)
    ctx.emit("attach complete", 100)
    return {"launch_id": launch_id, "session_id": cfg.capture.active_session_id}


def capture(ctx: OperationContext, output_dir: str | Path, timeout_seconds: int) -> dict:
    cfg = ctx.cfg()
    ctx.emit("triggering capture", 20)
    service = CaptureService(cfg, capture_bridge_client(cfg, start_qrenderdoc=False), MuMu12(cfg))
    rdc_path = service.capture(output_dir, timeout_seconds=timeout_seconds)
    save_config(cfg)
    ctx.emit("capture complete", 100)
    return {"rdc_path": str(rdc_path)}


def export_assets(ctx: OperationContext, rdc_path: str | Path, output_dir: str | Path, assets: str) -> dict:
    cfg = ctx.cfg()
    ctx.emit("starting RenderDocMCP", 15)
    manifest = ExportService(mcp_client(cfg)).export(rdc_path, output_dir, assets)
    save_config(cfg)
    ctx.emit("export complete", 100)
    return {"manifest": manifest, "output_dir": str(output_dir)}


def release_session(ctx: OperationContext) -> dict:
    cfg = ctx.cfg()
    cfg.capture.active_session_id = None
    cfg.capture.active_launch_id = ""
    cfg.capture.active_pid = None
    cfg.capture.active_session_started_at = None
    save_config(cfg)
    return {"released": True}


def start_mcp(ctx: OperationContext) -> dict:
    cfg = ctx.cfg()
    client = mcp_client(cfg)
    client.ping()
    save_config(cfg)
    return {"running": True, "version": cfg.mcp.release_tag or cfg.mcp.asset_name or "unknown"}


def stop_mcp(ctx: OperationContext) -> dict:
    cfg = ctx.cfg()
    if cfg.capture.active_session_id:
        raise UserActionRequired("Active capture session exists. Release the session before stopping MCP.")
    stop_standalone_mcp_bridge(cfg.mcp.executable_path)
    if is_process_running("qrenderdoc.exe"):
        terminate_process_tree("qrenderdoc.exe")
    return {"running": False}


def restart_mcp(ctx: OperationContext) -> dict:
    stop_mcp(ctx)
    return start_mcp(ctx)


def mcp_client(cfg: AppConfig, require_capture_connect: bool = False) -> FileIpcMcpClient:
    if not RenderDocInstaller(cfg).ensure_installed():
        raise DependencyMissing("RenderDoc v1.44 was not found. Run setup before this action.")
    mcp_exe = McpInstaller(cfg).runtime_executable()
    cfg.mcp.executable_path = str(mcp_exe)
    qrenderdoc_running = is_process_running("qrenderdoc.exe")
    if cfg.mcp.extension_patch_restart_required:
        if qrenderdoc_running:
            raise UserActionRequired("RenderDocMCP was updated. Close all RenderDoc windows, then retry.")
        cfg.mcp.extension_patch_restart_required = False

    patch_applied = patch_renderdoc_mcp_extension(mcp_exe)
    if patch_applied:
        cfg.mcp.extension_patch_restart_required = qrenderdoc_running
        if qrenderdoc_running:
            raise UserActionRequired("RenderDocMCP was updated. Close all RenderDoc windows, then retry.")

    stop_standalone_mcp_bridge(mcp_exe)
    start_qrenderdoc(cfg)
    client = FileIpcMcpClient(
        executable_path=None,
        process_alive=lambda: count_processes("qrenderdoc.exe") == 1,
        process_description="qrenderdoc.exe",
    )
    wait_for_mcp(client)
    if require_capture_connect:
        ensure_capture_connect_capability(client)
    return client


def capture_bridge_client(cfg: AppConfig, start_qrenderdoc: bool) -> CaptureBridgeClient:
    if not RenderDocInstaller(cfg).ensure_installed():
        raise DependencyMissing("RenderDoc v1.44 was not found. Run setup before this action.")
    bridge_installer = CaptureBridgeInstaller()
    bridge_installer.install()
    running_count = count_processes("qrenderdoc.exe")
    if running_count > 1:
        raise UserActionRequired("Multiple qrenderdoc.exe instances are running. Close extra RenderDoc windows and retry.")
    if running_count == 0:
        if not start_qrenderdoc:
            raise UserActionRequired("No qrenderdoc.exe is running. Run attach first.")
        start_qrenderdoc_process(cfg, python_script=bridge_installer.bootstrap_script())
    client = CaptureBridgeClient()
    wait_for_capture_bridge(client)
    return client


def start_qrenderdoc(cfg: AppConfig) -> None:
    start_qrenderdoc_process(cfg, python_script=None)


def start_qrenderdoc_process(cfg: AppConfig, python_script: Path | None = None) -> None:
    qrenderdoc = Path(cfg.renderdoc.qrenderdoc_path)
    if not qrenderdoc.is_file():
        raise DependencyMissing(f"qrenderdoc.exe was not found: {qrenderdoc}")
    running_count = count_processes("qrenderdoc.exe")
    if running_count > 1:
        raise UserActionRequired("Multiple qrenderdoc.exe instances are running. Close extra RenderDoc windows and retry.")
    if running_count == 1:
        return
    kwargs = {"cwd": str(qrenderdoc.parent), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    args = [str(qrenderdoc)]
    if python_script is not None:
        args.extend(["--python", str(python_script)])
    subprocess.Popen(args, **kwargs)


def stop_standalone_mcp_bridge(executable_path: str | Path) -> None:
    names = {"renderdoc-mcp.exe", "RenderDocMCP.exe"}
    executable_name = Path(executable_path).name if executable_path else ""
    if executable_name:
        names.add(executable_name)
    for image_name in sorted(names, key=str.lower):
        if image_name.lower() == "qrenderdoc.exe":
            continue
        if count_processes(image_name) > 0:
            terminate_process_tree(image_name)


def wait_for_mcp(client: FileIpcMcpClient, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if client.ping():
                return
        except McpCapabilityMissing:
            return
        except (FileNotFoundError, TimeoutError, RdcAutoError) as exc:
            last_error = exc
        time.sleep(0.25)
    detail = f": {last_error}" if last_error else ""
    raise DependencyMissing(f"RenderDocMCP did not become ready within {int(timeout_seconds)} seconds{detail}")


def wait_for_capture_bridge(client: CaptureBridgeClient, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if client.ping():
                return
        except (FileNotFoundError, TimeoutError, RdcAutoError) as exc:
            last_error = exc
        time.sleep(0.25)
    detail = f": {last_error}" if last_error else ""
    raise DependencyMissing(f"rdc-auto capture bridge did not become ready within {int(timeout_seconds)} seconds{detail}")


def ensure_capture_connect_capability(client: FileIpcMcpClient) -> None:
    try:
        client.call("list_running_targets", timeout=5.0)
    except McpCapabilityMissing as exc:
        raise UserActionRequired("The running RenderDoc window is using an older extension. Close all RenderDoc windows, then retry.") from exc
```

- [ ] **Step 7: Change CLI to delegate to shared operations**

Modify `rdc_auto/cli.py` so `_cmd_setup`, `_cmd_attach`, `_cmd_capture`, and `_cmd_export` call `rdc_auto.operations` functions. Keep CLI argument parsing unchanged.

The handlers should follow this shape:

```python
from .operations import OperationContext, attach as op_attach, capture as op_capture, export_assets as op_export_assets, setup_environment


def _cmd_setup(cfg) -> None:
    setup_environment(OperationContext(config=cfg))
    print("setup complete")
```

Apply the same pattern for attach, capture, and export, preserving existing stdout messages.

- [ ] **Step 8: Run shared operation and CLI tests**

Run:

```powershell
python -m pytest tests/test_processes.py tests/test_operations.py tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add rdc_auto/processes.py rdc_auto/operations.py rdc_auto/config.py rdc_auto/cli.py tests/test_processes.py tests/test_operations.py tests/test_cli.py
git commit -m "refactor: share rdc-auto operations with GUI"
```

---

### Task 3: Status Snapshot and Config Extensions

**Files:**
- Modify: `rdc_auto/config.py`
- Create: `rdc_auto/gui/status.py`
- Modify: `tests/test_config.py`
- Create: `tests/test_gui_bridge.py`

- [ ] **Step 1: Write failing config tests for GUI fields**

Append to `tests/test_config.py`:

```python
def test_default_config_has_gui_ai_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    cfg = load_config()

    assert cfg.gui.window_width == 1320
    assert cfg.gui.window_height == 860
    assert cfg.ai.provider == "openai"
    assert cfg.ai.model == "gpt-4.1-mini"
    assert cfg.ai.base_url == "https://api.openai.com/v1"
    assert cfg.ai.api_key == ""
    assert cfg.capture.active_launch_id == ""
```

- [ ] **Step 2: Run config tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_config.py -v
```

Expected: FAIL because `AppConfig` has no `gui` or `ai` sections.

- [ ] **Step 3: Add GUI and AI config dataclasses**

Modify `rdc_auto/config.py`:

```python
@dataclass
class GuiConfig:
    window_width: int = 1320
    window_height: int = 860
    last_view: str = "dashboard"


@dataclass
class AiConfig:
    provider: str = "openai"
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
```

Add fields to `AppConfig`:

```python
gui: GuiConfig = field(default_factory=GuiConfig)
ai: AiConfig = field(default_factory=AiConfig)
```

Update `_from_dict`:

```python
gui=GuiConfig(**{**asdict(default.gui), **raw.get("gui", {})}),
ai=AiConfig(**{**asdict(default.ai), **raw.get("ai", {})}),
```

- [ ] **Step 4: Write failing status snapshot tests**

Create `tests/test_gui_bridge.py`:

```python
from __future__ import annotations

from rdc_auto.config import AppConfig
from rdc_auto.gui.status import build_status_snapshot


def test_build_status_snapshot_contains_topbar_sections(tmp_path):
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(tmp_path / "qrenderdoc.exe")
    cfg.mcp.executable_path = str(tmp_path / "RenderDocMCP.exe")
    cfg.emulator.root_dir = str(tmp_path / "MuMu")
    cfg.capture.active_launch_id = "launch-1"

    snapshot = build_status_snapshot(cfg, process_counts={"qrenderdoc.exe": 1})

    assert snapshot["renderdoc"]["path"].endswith("qrenderdoc.exe")
    assert snapshot["mcp"]["running"] is True
    assert snapshot["session"]["attached"] is True
    assert snapshot["session"]["launch_id"] == "launch-1"
    assert snapshot["config_preview"]["capture"]["active_launch_id"] == "launch-1"
```

- [ ] **Step 5: Run status test to verify it fails**

Run:

```powershell
python -m pytest tests/test_gui_bridge.py -v
```

Expected: FAIL because `rdc_auto.gui.status` does not exist.

- [ ] **Step 6: Implement status snapshot**

Create `rdc_auto/gui/status.py`:

```python
from __future__ import annotations

from dataclasses import asdict

from rdc_auto.config import AppConfig
from rdc_auto.processes import count_processes
from rdc_auto.renderdoc_installer import RENDERDOC_VERSION


def build_status_snapshot(cfg: AppConfig, process_counts: dict[str, int] | None = None) -> dict:
    counts = process_counts or {}

    def process_count(name: str) -> int:
        if name in counts:
            return counts[name]
        return count_processes(name)

    renderdoc_ready = bool(cfg.renderdoc.qrenderdoc_path)
    mcp_ready = bool(cfg.mcp.executable_path)
    mcp_running = process_count("qrenderdoc.exe") == 1 or process_count("RenderDocMCP.exe") > 0
    session_attached = bool(cfg.capture.active_session_id or cfg.capture.active_launch_id)
    config_preview = asdict(cfg)
    if config_preview.get("ai", {}).get("api_key"):
        config_preview["ai"]["api_key"] = "********"

    return {
        "renderdoc": {
            "ready": renderdoc_ready,
            "version": cfg.renderdoc.version or RENDERDOC_VERSION,
            "path": cfg.renderdoc.qrenderdoc_path,
        },
        "mumu": {
            "ready": bool(cfg.emulator.root_dir),
            "root_dir": cfg.emulator.root_dir,
            "vm_index": cfg.emulator.vm_index,
            "graphics_api": cfg.emulator.graphics_api,
        },
        "mcp": {
            "ready": mcp_ready,
            "running": mcp_running,
            "version": cfg.mcp.release_tag or cfg.mcp.asset_name or "unknown",
            "path": cfg.mcp.executable_path,
            "extension_loaded": mcp_running and not cfg.mcp.extension_patch_restart_required,
        },
        "session": {
            "attached": session_attached,
            "session_id": cfg.capture.active_session_id,
            "launch_id": cfg.capture.active_launch_id,
            "pid": cfg.capture.active_pid,
        },
        "paths": {
            "last_rdc_path": cfg.capture.last_rdc_path,
            "last_output_dir": cfg.capture.last_output_dir,
        },
        "ai": {
            "provider": cfg.ai.provider,
            "model": cfg.ai.model,
            "base_url": cfg.ai.base_url,
            "api_key_saved": bool(cfg.ai.api_key),
        },
        "config_preview": config_preview,
    }
```

- [ ] **Step 7: Run config and status tests**

Run:

```powershell
python -m pytest tests/test_config.py tests/test_gui_bridge.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add rdc_auto/config.py rdc_auto/gui/status.py tests/test_config.py tests/test_gui_bridge.py
git commit -m "feat: add GUI status and AI config state"
```

---

### Task 4: Background Job Manager

**Files:**
- Create: `rdc_auto/gui/jobs.py`
- Create: `tests/test_gui_jobs.py`

- [ ] **Step 1: Write failing job manager tests**

Create `tests/test_gui_jobs.py`:

```python
from __future__ import annotations

from rdc_auto.gui.jobs import JobManager


def test_job_manager_records_success():
    manager = JobManager(run_inline=True)

    job = manager.start("sample", lambda emit: {"value": 7})

    assert job["state"] == "queued"
    current = manager.get(job["job_id"])
    assert current["state"] == "succeeded"
    assert current["result"] == {"value": 7}
    assert current["progress"] == 100


def test_job_manager_records_failure():
    manager = JobManager(run_inline=True)

    def fail(emit):
        emit("starting", 10)
        raise ValueError("bad input")

    job = manager.start("sample", fail)
    current = manager.get(job["job_id"])

    assert current["state"] == "failed"
    assert current["error"]["type"] == "ValueError"
    assert current["error"]["message"] == "bad input"
    assert current["logs"] == ["starting"]
```

- [ ] **Step 2: Run job tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_gui_jobs.py -v
```

Expected: FAIL because `rdc_auto.gui.jobs` does not exist.

- [ ] **Step 3: Implement job manager**

Create `rdc_auto/gui/jobs.py`:

```python
from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable


JobCallable = Callable[[Callable[[str, int], None]], dict]


class JobManager:
    def __init__(self, run_inline: bool = False):
        self.run_inline = run_inline
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def start(self, action: str, fn: JobCallable) -> dict:
        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "action": action,
            "state": "queued",
            "progress": 0,
            "logs": [],
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            self._jobs[job_id] = job
        if self.run_inline:
            self._run(job_id, fn)
        else:
            thread = threading.Thread(target=self._run, args=(job_id, fn), daemon=True)
            thread.start()
        return dict(job)

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return {
                    "job_id": job_id,
                    "action": "",
                    "state": "missing",
                    "progress": 0,
                    "logs": [],
                    "result": None,
                    "error": {"type": "JobMissing", "message": f"Unknown job: {job_id}"},
                }
            return dict(job)

    def _run(self, job_id: str, fn: JobCallable) -> None:
        self._update(job_id, state="running", progress=1)

        def emit(message: str, progress: int) -> None:
            with self._lock:
                job = self._jobs[job_id]
                job["logs"].append(message)
                job["progress"] = max(job["progress"], min(99, int(progress)))
                job["updated_at"] = time.time()

        try:
            result = fn(emit)
        except Exception as exc:
            self._update(
                job_id,
                state="failed",
                error={"type": type(exc).__name__, "message": str(exc), "action_required": type(exc).__name__ == "UserActionRequired"},
            )
            return
        self._update(job_id, state="succeeded", progress=100, result=result)

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(changes)
            job["updated_at"] = time.time()
```

- [ ] **Step 4: Run job tests**

Run:

```powershell
python -m pytest tests/test_gui_jobs.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/gui/jobs.py tests/test_gui_jobs.py
git commit -m "feat: add GUI background job manager"
```

---

### Task 5: JavaScript Bridge API

**Files:**
- Create: `rdc_auto/gui/bridge.py`
- Modify: `tests/test_gui_bridge.py`

- [ ] **Step 1: Write failing bridge API tests**

Append to `tests/test_gui_bridge.py`:

```python
from rdc_auto.gui.bridge import GuiBridge


def test_bridge_get_status_returns_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.get_status({})

    assert response["ok"] is True
    assert "renderdoc" in response["data"]
    assert response["logs"] == []


def test_bridge_save_environment_updates_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_environment(
        {
            "renderdoc_path": "C:\\Program Files\\RenderDoc\\qrenderdoc.exe",
            "mumu_root": "D:\\MuMu",
            "vm_index": "1",
            "graphics_api": "vulkan",
        }
    )

    assert response["ok"] is True
    assert response["data"]["mumu"]["vm_index"] == "1"
```

- [ ] **Step 2: Run bridge tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_gui_bridge.py -v
```

Expected: FAIL because `rdc_auto.gui.bridge` does not exist.

- [ ] **Step 3: Implement bridge envelope and direct config methods**

Create `rdc_auto/gui/bridge.py`:

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from rdc_auto.config import load_config, save_config
from rdc_auto.errors import UserActionRequired
from rdc_auto.gui.jobs import JobManager
from rdc_auto.gui.status import build_status_snapshot
from rdc_auto.operations import (
    OperationContext,
    attach,
    capture,
    check_environment,
    export_assets,
    release_session,
    restart_mcp,
    setup_environment,
    start_mcp,
    stop_mcp,
)


class GuiBridge:
    def __init__(self, run_jobs_inline: bool = False):
        self.window = None
        self.jobs = JobManager(run_inline=run_jobs_inline)

    def bind_window(self, window) -> None:
        self.window = window

    def get_status(self, payload: dict | None = None) -> dict:
        return self._ok(build_status_snapshot(load_config()))

    def save_environment(self, payload: dict) -> dict:
        cfg = load_config()
        cfg.renderdoc.qrenderdoc_path = str(payload.get("renderdoc_path", "")).strip()
        cfg.emulator.root_dir = str(payload.get("mumu_root", "")).strip()
        cfg.emulator.vm_index = str(payload.get("vm_index", "")).strip()
        cfg.emulator.graphics_api = str(payload.get("graphics_api", "vulkan")).strip() or "vulkan"
        save_config(cfg)
        return self._ok(build_status_snapshot(cfg), logs=["environment config saved"])

    def save_mcp(self, payload: dict) -> dict:
        cfg = load_config()
        cfg.mcp.executable_path = str(payload.get("mcp_path", "")).strip()
        save_config(cfg)
        return self._ok(build_status_snapshot(cfg), logs=["MCP config saved"])

    def save_ai(self, payload: dict) -> dict:
        cfg = load_config()
        cfg.ai.provider = str(payload.get("provider", "openai")).strip() or "openai"
        cfg.ai.model = str(payload.get("model", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
        cfg.ai.base_url = str(payload.get("base_url", "https://api.openai.com/v1")).strip() or "https://api.openai.com/v1"
        cfg.ai.api_key = ""
        save_config(cfg)
        return self._ok(build_status_snapshot(cfg), logs=["AI settings saved without persisting API key"])

    def test_ai(self, payload: dict | None = None) -> dict:
        return self._ok({"connected": True, "mode": "frontend-only"}, logs=["AI test uses local GUI mode"])

    def send_chat(self, payload: dict) -> dict:
        message = str(payload.get("message", "")).strip()
        reply = _local_ai_reply(message)
        return self._ok({"reply": reply}, logs=[f"AI local reply: {message}"])

    def start_job(self, payload: dict) -> dict:
        action = str(payload.get("action", ""))
        params = payload.get("params", {}) if isinstance(payload.get("params", {}), dict) else {}
        actions: dict[str, Callable[[Callable[[str, int], None]], dict]] = {
            "check_environment": lambda emit: check_environment(OperationContext(progress=emit)),
            "setup": lambda emit: setup_environment(OperationContext(progress=emit)),
            "start_mcp": lambda emit: start_mcp(OperationContext(progress=emit)),
            "stop_mcp": lambda emit: stop_mcp(OperationContext(progress=emit)),
            "restart_mcp": lambda emit: restart_mcp(OperationContext(progress=emit)),
            "attach": lambda emit: attach(
                OperationContext(progress=emit),
                force=bool(params.get("force")),
                confirm_vulkan=bool(params.get("confirm_vulkan")),
                vm_index=str(params.get("vm_index", "")),
            ),
            "capture": lambda emit: capture(
                OperationContext(progress=emit),
                output_dir=str(params.get("output_dir", "")),
                timeout_seconds=int(params.get("timeout_seconds", 60)),
            ),
            "export": lambda emit: export_assets(
                OperationContext(progress=emit),
                rdc_path=str(params.get("rdc_path", "")),
                output_dir=str(params.get("output_dir", "")),
                assets=str(params.get("assets", "both")),
            ),
            "release_session": lambda emit: release_session(OperationContext(progress=emit)),
        }
        fn = actions.get(action)
        if fn is None:
            return self._fail(ValueError(f"Unsupported GUI action: {action}"))
        return self._ok(self.jobs.start(action, fn))

    def get_job(self, payload: dict) -> dict:
        return self._ok(self.jobs.get(str(payload.get("job_id", ""))))

    def choose_directory(self, payload: dict | None = None) -> dict:
        if self.window is None:
            return self._fail(UserActionRequired("The GUI window is not ready."))
        import webview

        result = self.window.create_file_dialog(webview.FOLDER_DIALOG, directory=str((payload or {}).get("initial_dir", "")))
        return self._ok({"path": result[0] if result else ""})

    def choose_file(self, payload: dict | None = None) -> dict:
        if self.window is None:
            return self._fail(UserActionRequired("The GUI window is not ready."))
        import webview

        result = self.window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=("RenderDoc Capture (*.rdc)",))
        return self._ok({"path": result[0] if result else ""})

    def open_path(self, payload: dict) -> dict:
        path = Path(str(payload.get("path", "")))
        if not path.exists():
            return self._fail(FileNotFoundError(str(path)))
        os.startfile(str(path))
        return self._ok({"opened": str(path)})

    @staticmethod
    def _ok(data: dict, logs: list[str] | None = None) -> dict:
        return {"ok": True, "data": data, "logs": logs or []}

    @staticmethod
    def _fail(exc: Exception, logs: list[str] | None = None) -> dict:
        return {
            "ok": False,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "action_required": isinstance(exc, UserActionRequired),
            },
            "logs": logs or [],
        }


def _local_ai_reply(message: str) -> str:
    lower = message.lower()
    if "attach" in lower:
        return "建议先确认 MuMu12 已切换到 Vulkan，并关闭多余的 qrenderdoc.exe 实例。"
    if "mcp" in lower:
        return "建议在资源导出页先执行检测 MCP；如果提示扩展需要重启，请关闭 RenderDoc 后重试。"
    if "export" in lower or "导出" in message:
        return "建议确认 RDC 文件存在、MCP 运行中，并检查输出目录是否可写。"
    return "建议先查看顶部状态栏和底部日志，按环境设置、Attach、捕捉、导出的顺序排查。"
```

- [ ] **Step 4: Run bridge tests**

Run:

```powershell
python -m pytest tests/test_gui_bridge.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/gui/bridge.py tests/test_gui_bridge.py
git commit -m "feat: expose GUI bridge API"
```

---

### Task 6: Desktop Window Entry Point

**Files:**
- Create: `rdc_auto/gui/app.py`
- Create: `rdc_auto/gui/__main__.py`
- Modify: `tests/test_gui_static.py`

- [ ] **Step 1: Write failing app entry test**

Append to `tests/test_gui_static.py`:

```python
from rdc_auto.gui.app import build_window_options


def test_build_window_options_points_to_packaged_index():
    options = build_window_options()

    assert options["title"] == "RdcAutomation"
    assert options["url"].endswith("index.html")
    assert options["width"] == 1320
    assert options["height"] == 860
```

- [ ] **Step 2: Run app entry test to verify it fails**

Run:

```powershell
python -m pytest tests/test_gui_static.py -v
```

Expected: FAIL because `rdc_auto.gui.app` does not exist.

- [ ] **Step 3: Implement pywebview app entry**

Create `rdc_auto/gui/app.py`:

```python
from __future__ import annotations

from rdc_auto.config import load_config
from rdc_auto.gui.bridge import GuiBridge
from rdc_auto.gui.paths import gui_index_path


def build_window_options() -> dict:
    cfg = load_config()
    return {
        "title": "RdcAutomation",
        "url": str(gui_index_path()),
        "width": int(cfg.gui.window_width),
        "height": int(cfg.gui.window_height),
        "min_size": (1100, 720),
    }


def main(debug: bool = False) -> int:
    import webview

    bridge = GuiBridge()
    options = build_window_options()
    window = webview.create_window(
        options["title"],
        options["url"],
        js_api=bridge,
        width=options["width"],
        height=options["height"],
        min_size=options["min_size"],
    )
    bridge.bind_window(window)
    webview.start(debug=debug)
    return 0
```

Create `rdc_auto/gui/__main__.py`:

```python
from __future__ import annotations

from rdc_auto.gui.app import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run GUI static tests**

Run:

```powershell
python -m pytest tests/test_gui_static.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rdc_auto/gui/app.py rdc_auto/gui/__main__.py tests/test_gui_static.py
git commit -m "feat: add GUI desktop entry point"
```

---

### Task 7: Frontend Bridge Integration

**Files:**
- Modify: `rdc_auto/gui/static/index.html`
- Modify: `tests/test_gui_static.py`

- [ ] **Step 1: Write failing frontend integration tests**

Append to `tests/test_gui_static.py`:

```python
def test_gui_index_has_backend_action_mapping():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "function callBackend" in html
    assert "function runJobAction" in html
    assert '"check-env": "check_environment"' in html
    assert '"attach": "attach"' in html
    assert '"capture": "capture"' in html
    assert '"export": "export"' in html
    assert 'window.RdcBackend.call("start_job"' in html
```

- [ ] **Step 2: Run frontend test to verify it fails**

Run:

```powershell
python -m pytest tests/test_gui_static.py::test_gui_index_has_backend_action_mapping -v
```

Expected: FAIL because the prototype still uses mock-only handlers.

- [ ] **Step 3: Add backend helpers inside the existing script**

In `rdc_auto/gui/static/index.html`, add these functions near the existing `log` and `toast` helpers:

```javascript
    function callBackend(method, payload) {
      return window.RdcBackend.call(method, payload || {}).then((response) => {
        if (response.logs) response.logs.forEach((line) => log(line));
        if (!response.ok) {
          const message = response.error && response.error.message ? response.error.message : "未知错误";
          toast("操作失败", message);
          log(`ERROR ${message}`);
        }
        return response;
      });
    }

    const backendJobActions = {
      "check-env": "check_environment",
      "install-env": "setup",
      "check-mcp": "start_mcp",
      "start-mcp": "start_mcp",
      "stop-mcp": "stop_mcp",
      "restart-mcp": "restart_mcp",
      "install-mcp": "setup",
      "quick-attach": "attach",
      "attach": "attach",
      "quick-capture": "capture",
      "capture": "capture",
      "release-session": "release_session",
      "export": "export"
    };

    function runJobAction(action, params, progressSelector, done) {
      return callBackend("start_job", { action, params: params || {} }).then((response) => {
        if (!response.ok) return response;
        const jobId = response.data.job_id;
        const progress = progressSelector ? $(progressSelector) : null;
        const bar = progress ? progress.querySelector("span") : null;
        if (progress && bar) {
          progress.classList.add("active");
          bar.style.width = "1%";
        }
        const timer = window.setInterval(() => {
          callBackend("get_job", { job_id: jobId }).then((jobResponse) => {
            if (!jobResponse.ok) {
              window.clearInterval(timer);
              if (progress) progress.classList.remove("active");
              return;
            }
            const job = jobResponse.data;
            if (bar) bar.style.width = `${job.progress || 0}%`;
            if (job.state === "succeeded") {
              window.clearInterval(timer);
              if (progress) progress.classList.remove("active");
              if (done) done(job.result || {});
              refreshStatusFromBackend();
            }
            if (job.state === "failed") {
              window.clearInterval(timer);
              if (progress) progress.classList.remove("active");
              const message = job.error && job.error.message ? job.error.message : "任务失败";
              toast("任务失败", message);
              log(`ERROR ${message}`);
            }
          });
        }, 350);
        return response;
      });
    }
```

- [ ] **Step 4: Add status hydration**

Add:

```javascript
    function refreshStatusFromBackend() {
      return callBackend("get_status", {}).then((response) => {
        if (!response.ok) {
          updateStatus();
          return;
        }
        applyBackendStatus(response.data);
      });
    }

    function applyBackendStatus(snapshot) {
      state.renderdocReady = Boolean(snapshot.renderdoc.ready);
      state.mumuReady = Boolean(snapshot.mumu.ready);
      state.mcpReady = Boolean(snapshot.mcp.ready);
      state.mcpRunning = Boolean(snapshot.mcp.running);
      state.mcpExtensionLoaded = Boolean(snapshot.mcp.extension_loaded);
      state.mcpVersion = snapshot.mcp.version || state.mcpVersion;
      state.sessionAttached = Boolean(snapshot.session.attached);
      state.lastRdcPath = snapshot.paths.last_rdc_path || state.lastRdcPath;
      if ($("#renderdocPath")) $("#renderdocPath").value = snapshot.renderdoc.path || $("#renderdocPath").value;
      if ($("#mumuRoot")) $("#mumuRoot").value = snapshot.mumu.root_dir || $("#mumuRoot").value;
      if ($("#vmIndex")) $("#vmIndex").value = snapshot.mumu.vm_index || $("#vmIndex").value;
      if ($("#mcpPath")) $("#mcpPath").value = snapshot.mcp.path || $("#mcpPath").value;
      if ($("#rdcPath") && state.lastRdcPath) $("#rdcPath").value = state.lastRdcPath;
      if ($("#eidRdcPath") && state.lastRdcPath) $("#eidRdcPath").value = state.lastRdcPath;
      if ($("#configPreview")) $("#configPreview").value = JSON.stringify(snapshot.config_preview, null, 2);
      updateStatus();
    }
```

- [ ] **Step 5: Route existing actions to backend jobs**

At the top of `handleAction(action)`, before the `switch`, add:

```javascript
      if (window.RdcBackend.available() && backendJobActions[action]) {
        const params = collectActionParams(action);
        const progressSelector = progressSelectorForAction(action);
        return runJobAction(backendJobActions[action], params, progressSelector, (result) => {
          if (result.rdc_path) {
            state.lastRdcPath = result.rdc_path;
            $("#rdcPath").value = result.rdc_path;
            $("#eidRdcPath").value = result.rdc_path;
          }
          toast("操作完成", action);
        });
      }
```

Add helpers:

```javascript
    function collectActionParams(action) {
      if (action === "attach" || action === "quick-attach") {
        return {
          vm_index: $("#attachVmIndex")?.value || $("#vmIndex")?.value || "",
          force: Boolean($("#forceCloseMumu")?.checked),
          confirm_vulkan: Boolean($("#attachVulkan")?.checked || $("#vulkanConfirmed")?.checked)
        };
      }
      if (action === "capture" || action === "quick-capture") {
        return {
          output_dir: $("#captureOut")?.value || "",
          timeout_seconds: Number($("#captureTimeout")?.value || 60)
        };
      }
      if (action === "export") {
        return {
          rdc_path: $("#rdcPath")?.value || "",
          output_dir: $("#exportOut")?.value || "",
          assets: $("#assetType")?.value || "both"
        };
      }
      return {};
    }

    function progressSelectorForAction(action) {
      if (action.includes("env") || action.includes("mcp")) return "#envProgress";
      if (action.includes("attach")) return "#attachProgress";
      if (action.includes("capture")) return "#captureProgress";
      if (action.includes("export")) return "#exportProgress";
      return "";
    }
```

- [ ] **Step 6: Wire save and AI actions directly**

In `handleAction`, before falling back to mock switch cases:

```javascript
      if (window.RdcBackend.available() && action === "save-env") {
        return callBackend("save_environment", {
          renderdoc_path: $("#renderdocPath")?.value || "",
          mumu_root: $("#mumuRoot")?.value || "",
          vm_index: $("#vmIndex")?.value || "",
          graphics_api: $("#graphicsApi")?.value || "vulkan"
        }).then((response) => response.ok && applyBackendStatus(response.data));
      }
      if (window.RdcBackend.available() && action === "save-mcp") {
        return callBackend("save_mcp", { mcp_path: $("#mcpPath")?.value || "" })
          .then((response) => response.ok && applyBackendStatus(response.data));
      }
      if (window.RdcBackend.available() && action === "save-ai") {
        return callBackend("save_ai", {
          provider: $("#aiProvider")?.value || "openai",
          model: $("#aiModel")?.value || "",
          base_url: $("#aiBaseUrl")?.value || "",
          api_key: $("#aiKey")?.value || ""
        });
      }
      if (window.RdcBackend.available() && action === "test-ai") {
        return callBackend("test_ai", {}).then((response) => response.ok && toast("AI 连接测试", "当前为本地前端模式。"));
      }
```

- [ ] **Step 7: Hydrate status on startup**

Replace final startup call:

```javascript
    updateStatus();
```

with:

```javascript
    if (window.RdcBackend.available()) {
      refreshStatusFromBackend();
    } else {
      updateStatus();
    }
```

- [ ] **Step 8: Run frontend integration tests**

Run:

```powershell
python -m pytest tests/test_gui_static.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add rdc_auto/gui/static/index.html tests/test_gui_static.py
git commit -m "feat: connect prototype actions to GUI backend"
```

---

### Task 8: File and Folder Dialogs

**Files:**
- Modify: `rdc_auto/gui/bridge.py`
- Modify: `rdc_auto/gui/static/index.html`
- Modify: `tests/test_gui_bridge.py`
- Modify: `tests/test_gui_static.py`

- [ ] **Step 1: Write failing tests for dialog bridge constants**

Append to `tests/test_gui_bridge.py`:

```python
class FakeWindow:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.calls.append((dialog_type, kwargs))
        return self.result


def test_choose_directory_uses_window_dialog(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)
    bridge.bind_window(FakeWindow([str(tmp_path)]))

    response = bridge.choose_directory({"initial_dir": str(tmp_path)})

    assert response["ok"] is True
    assert response["data"]["path"] == str(tmp_path)
```

- [ ] **Step 2: Run bridge dialog test**

Run:

```powershell
python -m pytest tests/test_gui_bridge.py::test_choose_directory_uses_window_dialog -v
```

Expected: PASS.

- [ ] **Step 3: Write failing frontend dialog test**

Append to `tests/test_gui_static.py`:

```python
def test_gui_index_routes_choose_actions_to_backend_dialogs():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'action === "choose-mumu"' in html
    assert 'callBackend("choose_directory"' in html
    assert 'action === "choose-rdc"' in html
    assert 'callBackend("choose_file"' in html
```

- [ ] **Step 4: Add frontend dialog routing**

In `handleAction`, before mock switch cases:

```javascript
      if (window.RdcBackend.available() && action === "choose-mumu") {
        return callBackend("choose_directory", { initial_dir: $("#mumuRoot")?.value || "" }).then((response) => {
          if (response.ok && response.data.path) $("#mumuRoot").value = response.data.path;
        });
      }
      if (window.RdcBackend.available() && action === "choose-capture-out") {
        return callBackend("choose_directory", { initial_dir: $("#captureOut")?.value || "" }).then((response) => {
          if (response.ok && response.data.path) $("#captureOut").value = response.data.path;
        });
      }
      if (window.RdcBackend.available() && action === "choose-rdc") {
        return callBackend("choose_file", {}).then((response) => {
          if (response.ok && response.data.path) {
            $("#rdcPath").value = response.data.path;
            $("#eidRdcPath").value = response.data.path;
          }
        });
      }
```

- [ ] **Step 5: Run dialog tests**

Run:

```powershell
python -m pytest tests/test_gui_bridge.py tests/test_gui_static.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add rdc_auto/gui/bridge.py rdc_auto/gui/static/index.html tests/test_gui_bridge.py tests/test_gui_static.py
git commit -m "feat: add GUI file and folder dialogs"
```

---

### Task 9: EID Export Support

**Files:**
- Modify: `rdc_auto/export_assets.py`
- Modify: `rdc_auto/gui/bridge.py`
- Modify: `rdc_auto/gui/static/index.html`
- Modify: `tests/test_export_assets.py`
- Modify: `tests/test_gui_static.py`

- [ ] **Step 1: Write failing EID export service tests**

Append to `tests/test_export_assets.py`:

```python
def test_list_draw_calls_returns_event_rows(tmp_path):
    class FakeMcp:
        def call(self, method, params=None, timeout=None):
            assert method == "get_draw_calls"
            return {"draws": [{"event_id": 1203, "name": "Character.Draw"}]}

    rows = ExportService(FakeMcp()).list_draw_calls(tmp_path / "capture.rdc")

    assert rows == [{"event_id": 1203, "name": "Character.Draw"}]


def test_export_mesh_for_event_writes_obj(tmp_path):
    class FakeMcp:
        def call(self, method, params=None, timeout=None):
            if method == "open_capture":
                return {}
            if method == "export_mesh_to_file":
                Path(params["output_path"]).write_text(
                    '{"indices":[0,1,2],"position":[[0,0,0],[1,0,0],[0,1,0]]}',
                    encoding="utf-8",
                )
                return {"output_path": params["output_path"]}
            raise AssertionError(method)

    result = ExportService(FakeMcp()).export_mesh_for_event(tmp_path / "capture.rdc", tmp_path / "out", 1203)

    assert result["event_id"] == 1203
    assert Path(result["obj_path"]).is_file()
```

- [ ] **Step 2: Run EID tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_export_assets.py -v
```

Expected: FAIL because `ExportService` has no EID methods.

- [ ] **Step 3: Add EID service methods**

Modify `rdc_auto/export_assets.py`:

```python
    def list_draw_calls(self, rdc_path: str | Path) -> list[dict]:
        self.mcp.call("open_capture", {"capture_path": str(Path(rdc_path))}, timeout=120.0)
        draws = self.mcp.call("get_draw_calls", {"include_children": True, "only_actions": True}, timeout=60.0).get("draws", [])
        rows = []
        for draw in draws:
            raw_event_id = draw["event_id"] if "event_id" in draw else draw.get("eventId")
            try:
                event_id = _parse_event_id(raw_event_id)
            except ValueError:
                continue
            rows.append({"event_id": event_id, "name": str(draw.get("name") or f"draw_{event_id}")})
        return rows

    def export_mesh_for_event(self, rdc_path: str | Path, output_dir: str | Path, event_id: int) -> dict:
        event_id = _parse_event_id(event_id)
        output_dir = Path(output_dir)
        raw_dir = output_dir / "raw_mesh_json"
        meshes_dir = output_dir / "meshes"
        raw_dir.mkdir(parents=True, exist_ok=True)
        meshes_dir.mkdir(parents=True, exist_ok=True)
        self.mcp.call("open_capture", {"capture_path": str(Path(rdc_path))}, timeout=120.0)
        raw_json = raw_dir / f"{event_id}_eid.json"
        obj = meshes_dir / f"{event_id}_eid.obj"
        mtl = meshes_dir / f"{event_id}_eid.mtl"
        self.mcp.call("export_mesh_to_file", {"event_id": event_id, "output_path": str(raw_json)}, timeout=120.0)
        convert_mesh_json_to_obj(raw_json, obj, mtl, material_name=f"mat_{event_id}")
        return {"event_id": event_id, "raw_json_path": str(raw_json), "obj_path": str(obj), "mtl_path": str(mtl)}

    def export_bound_textures_for_event(self, rdc_path: str | Path, output_dir: str | Path, event_id: int) -> dict:
        event_id = _parse_event_id(event_id)
        output_dir = Path(output_dir)
        textures_dir = output_dir / "textures" / f"eid_{event_id}"
        textures_dir.mkdir(parents=True, exist_ok=True)
        self.mcp.call("open_capture", {"capture_path": str(Path(rdc_path))}, timeout=120.0)
        bound = self.mcp.call("get_bound_textures", {"event_id": event_id}, timeout=60.0).get("textures", [])
        exported = []
        for texture in bound:
            resource_id = str(texture.get("resource_id") or texture.get("id") or "")
            name = safe_name(str(texture.get("name") or "texture"))
            path = textures_dir / f"{name}_{safe_name(resource_id)}.png"
            self.mcp.call(
                "export_texture_to_file",
                {"resource_id": resource_id, "output_path": str(path), "file_type": "PNG"},
                timeout=120.0,
            )
            exported.append(str(path))
        return {"event_id": event_id, "textures": exported}
```

- [ ] **Step 4: Add bridge methods for EID actions**

In `rdc_auto/gui/bridge.py`, add:

```python
from rdc_auto.export_assets import ExportService
from rdc_auto.operations import mcp_client
```

Add methods:

```python
    def load_eid_list(self, payload: dict) -> dict:
        try:
            cfg = load_config()
            rows = ExportService(mcp_client(cfg)).list_draw_calls(str(payload.get("rdc_path", "")))
            return self._ok({"rows": rows}, logs=[f"loaded {len(rows)} EID rows"])
        except Exception as exc:
            return self._fail(exc)

    def export_eid_model(self, payload: dict) -> dict:
        try:
            cfg = load_config()
            result = ExportService(mcp_client(cfg)).export_mesh_for_event(
                str(payload.get("rdc_path", "")),
                str(payload.get("output_dir", "")),
                int(payload.get("event_id", 0)),
            )
            return self._ok(result, logs=[f"exported EID model {result['event_id']}"])
        except Exception as exc:
            return self._fail(exc)

    def export_eid_textures(self, payload: dict) -> dict:
        try:
            cfg = load_config()
            result = ExportService(mcp_client(cfg)).export_bound_textures_for_event(
                str(payload.get("rdc_path", "")),
                str(payload.get("output_dir", "")),
                int(payload.get("event_id", 0)),
            )
            return self._ok(result, logs=[f"exported EID textures {result['event_id']}"])
        except Exception as exc:
            return self._fail(exc)
```

- [ ] **Step 5: Wire frontend EID actions**

In `rdc_auto/gui/static/index.html`, route these actions before mock switch cases:

```javascript
      if (window.RdcBackend.available() && action === "load-eid-list") {
        return callBackend("load_eid_list", { rdc_path: $("#eidRdcPath")?.value || $("#rdcPath")?.value || "" }).then((response) => {
          if (response.ok) {
            eidRows.length = 0;
            response.data.rows.forEach((row) => eidRows.push({
              eid: row.event_id,
              name: row.name,
              mesh: "available",
              textures: "requires MCP support"
            }));
            renderEidTable();
            toast("EID 列表已加载", `${response.data.rows.length} 行`);
          }
        });
      }
      if (window.RdcBackend.available() && action === "export-eid-model") {
        return callBackend("export_eid_model", {
          rdc_path: $("#eidRdcPath")?.value || $("#rdcPath")?.value || "",
          output_dir: $("#exportOut")?.value || "",
          event_id: Number($("#eidInput")?.value || 0)
        }).then((response) => response.ok && toast("EID 模型导出完成", response.data.obj_path));
      }
      if (window.RdcBackend.available() && action === "export-eid-textures") {
        return callBackend("export_eid_textures", {
          rdc_path: $("#eidRdcPath")?.value || $("#rdcPath")?.value || "",
          output_dir: $("#exportOut")?.value || "",
          event_id: Number($("#eidInput")?.value || 0)
        }).then((response) => response.ok && toast("EID 贴图导出完成", `${response.data.textures.length} 个文件`));
      }
```

- [ ] **Step 6: Add static assertions for EID bridge**

Append to `tests/test_gui_static.py`:

```python
def test_gui_index_routes_eid_actions_to_backend():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'callBackend("load_eid_list"' in html
    assert 'callBackend("export_eid_model"' in html
    assert 'callBackend("export_eid_textures"' in html
```

- [ ] **Step 7: Run EID tests**

Run:

```powershell
python -m pytest tests/test_export_assets.py tests/test_gui_bridge.py tests/test_gui_static.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add rdc_auto/export_assets.py rdc_auto/gui/bridge.py rdc_auto/gui/static/index.html tests/test_export_assets.py tests/test_gui_static.py
git commit -m "feat: add GUI EID export actions"
```

---

### Task 10: GUI Packaging Script

**Files:**
- Create: `scripts/build_gui_exe.ps1`
- Modify: `README.md`
- Create: `docs/gui-manual-acceptance.md`

- [ ] **Step 1: Create GUI build script**

Create `scripts/build_gui_exe.ps1`:

```powershell
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

Invoke-Checked python -m PyInstaller `
  --onefile `
  --windowed `
  --name RdcAutomation `
  --collect-all webview `
  --add-data $addData `
  rdc_auto\gui\__main__.py

$exe = Join-Path $PWD "dist\RdcAutomation.exe"
if (-not (Test-Path $exe)) {
  throw "Expected executable was not produced: $exe"
}

Write-Host "Built $exe"
```

- [ ] **Step 2: Update README with GUI usage**

Add this section to `README.md` after the existing executable build section:

````markdown
## Build GUI Executable

```powershell
.\scripts\build_gui_exe.ps1
```

The desktop executable is written to `dist\RdcAutomation.exe`.

The GUI keeps the same workflow as the CLI: setup, attach, capture, and export. The AI assistant screen in the first GUI release stores UI settings and returns local diagnostic replies only.
````

- [ ] **Step 3: Create manual GUI acceptance checklist**

Create `docs/gui-manual-acceptance.md`:

```markdown
# RdcAutomation GUI Manual Acceptance

Run these checks on Windows with Python 3.11+, MuMu12, and the project source available.

## Build

1. Run `powershell -ExecutionPolicy Bypass -File scripts/build_gui_exe.ps1`.
2. Confirm `dist\RdcAutomation.exe` exists.
3. Launch `dist\RdcAutomation.exe`.
4. Confirm the first screen shows 工作台 and the top status row.

## Environment

1. Open 环境设置.
2. Set `qrenderdoc.exe` path.
3. Set MuMu12 root directory.
4. Set VM index.
5. Confirm Vulkan checkbox remains checked.
6. Save configuration.
7. Refresh status and confirm the config preview masks the AI key.

## MCP

1. Set RenderDocMCP executable path or run 安装/修复 MCP.
2. Run 检测 MCP from 资源导出.
3. Confirm the MCP status card changes to running.
4. Run 关闭 MCP after releasing any active session.

## Capture

1. Open 捕捉 RDC.
2. Run Attach 模拟器.
3. Wait until the job reaches 100%.
4. Run 捕捉当前帧.
5. Confirm the generated RDC path appears in 资源导出.

## Export

1. Open 资源导出.
2. Select an existing `.rdc`.
3. Choose both assets.
4. Run 开始导出.
5. Confirm `manifest.json`, `textures`, `meshes`, and `raw_mesh_json` are written.

## EID

1. Open 高级 EID.
2. Load DrawCall / EID list.
3. Select an event id.
4. Export that EID model.
5. If EID texture binding is unsupported by the installed MCP bridge, confirm the GUI shows a clear error.

## AI Screen

1. Open AI 助手.
2. Save provider/model/base URL settings.
3. Run 测试连接 and confirm it reports local GUI mode.
4. Send `为什么 attach 失败？`.
5. Confirm the reply suggests Vulkan and qrenderdoc checks.
```

- [ ] **Step 4: Run tests before building**

Run:

```powershell
python -m pytest -v
```

Expected: PASS.

- [ ] **Step 5: Build GUI executable**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_gui_exe.ps1
```

Expected: `dist\RdcAutomation.exe` exists.

- [ ] **Step 6: Commit**

```powershell
git add scripts/build_gui_exe.ps1 README.md docs/gui-manual-acceptance.md
git commit -m "build: add GUI executable packaging"
```

---

### Task 11: Final Verification

**Files:**
- No source files expected unless verification exposes a defect.

- [ ] **Step 1: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Build CLI executable**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
```

Expected: `dist\rdc-auto.exe` exists.

- [ ] **Step 3: Build GUI executable**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_gui_exe.ps1
```

Expected: `dist\RdcAutomation.exe` exists.

- [ ] **Step 4: Launch GUI smoke test**

Run:

```powershell
Start-Process -FilePath dist\RdcAutomation.exe
```

Expected: a desktop window opens with the same navigation and layout as `html-ui-prototype/index.html`.

- [ ] **Step 5: Check git status**

Run:

```powershell
git status --short
```

Expected: no uncommitted source, test, script, or docs changes from the GUI implementation.

## Self-Review

Spec coverage:

- HTML prototype page structure is preserved by Task 1 and Task 7.
- Workbench navigation, toasts, logs, progress bars, tabs, and modal behavior remain in the packaged `index.html`.
- Environment settings are handled by Task 3, Task 5, and Task 7.
- RenderDoc MCP status and controls are handled by Task 2, Task 5, and Task 7.
- Attach, capture, release session, and normal export are handled by Task 2, Task 5, and Task 7.
- EID listing and EID model export are handled by Task 9.
- EID bound-texture export has a concrete MCP call path and a concrete unsupported-capability error path in Task 9.
- AI assistant first-release behavior is handled by Task 3 and Task 5 without external network calls.
- EXE packaging is handled by Task 10 and verified by Task 11.

Incomplete-marker scan:

- The plan defines concrete first-release behavior for every prototype button.
- The AI assistant is intentionally local-only in this release.
- The EID texture path has a defined failure mode when the installed MCP bridge cannot provide bound texture data.

Type consistency:

- Bridge method names use snake_case: `get_status`, `save_environment`, `start_job`, `get_job`, `load_eid_list`, `export_eid_model`, `export_eid_textures`.
- Job action names match frontend `backendJobActions`: `setup`, `start_mcp`, `stop_mcp`, `restart_mcp`, `attach`, `capture`, `export`, `release_session`.
- Asset values remain `textures`, `meshes`, and `both`.
- Status keys remain `renderdoc`, `mumu`, `mcp`, `session`, `paths`, `ai`, and `config_preview`.
