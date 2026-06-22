from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .capture import CaptureService
from .capture_bridge import CaptureBridgeClient, CaptureBridgeInstaller
from .config import AppConfig, load_config
from .emulator import MuMu12
from .errors import DependencyMissing, McpCapabilityMissing, RdcAutoError, UserActionRequired
from .export_assets import ExportService
from .mcp_client import FileIpcMcpClient
from .mcp_installer import McpInstaller
from .mcp_patch import patch_renderdoc_mcp_extension
from .paths import canonical_mumu_root, validate_mumu_root
from .processes import count_processes, executable_name, is_process_running, terminate_process_tree
from .prompts import prompt_path
from .renderdoc_installer import RenderDocInstaller


@dataclass
class OperationContext:
    config: AppConfig | None = None
    progress: Callable[[str, int], None] | None = None

    def cfg(self) -> AppConfig:
        if self.config is None:
            self.config = load_config()
        return self.config

    def emit(self, message: str, percent: int) -> None:
        if self.progress is not None:
            self.progress(message, percent)


def setup_environment(ctx: OperationContext) -> None:
    cfg = ctx.cfg()
    ctx.emit("checking RenderDoc", 10)
    installer = RenderDocInstaller(cfg)
    if not installer.ensure_installed():
        url = installer.resolve_download_url()
        installer_path = installer.download_installer(url)
        installer.run_installer(installer_path)
        if not installer.ensure_installed():
            raise DependencyMissing("RenderDoc v1.44 installation completed, but qrenderdoc.exe with version 1.44 was not found.")

    ctx.emit("checking MuMu12", 55)
    ensure_mumu_root(cfg)

    ctx.emit("checking RenderDocMCP", 75)
    mcp = McpInstaller(cfg)
    mcp_exe = mcp.ensure_installed()
    cfg.mcp.executable_path = str(mcp_exe)
    ctx.emit("setup complete", 100)


def check_environment(ctx: OperationContext) -> dict:
    cfg = ctx.cfg()
    renderdoc_installed = RenderDocInstaller(cfg).ensure_installed()
    mcp_executable = ""
    mcp_installed = False
    try:
        mcp_exe = McpInstaller(cfg).runtime_executable()
        cfg.mcp.executable_path = str(mcp_exe)
        mcp_executable = str(mcp_exe)
        mcp_installed = True
    except (FileNotFoundError, ValueError):
        mcp_installed = False

    mumu_executable = ""
    mumu_configured = False
    if cfg.emulator.root_dir:
        try:
            mumu_executable = str(validate_mumu_root(canonical_mumu_root(cfg.emulator.root_dir, cfg.emulator.exe_relative_path), cfg.emulator.exe_relative_path))
            mumu_configured = True
        except FileNotFoundError:
            mumu_configured = False

    return {
        "renderdoc_installed": renderdoc_installed,
        "renderdoc_path": cfg.renderdoc.qrenderdoc_path,
        "mcp_installed": mcp_installed,
        "mcp_executable_path": mcp_executable,
        "mumu_configured": mumu_configured,
        "mumu_executable_path": mumu_executable,
        "qrenderdoc_running": is_process_running("qrenderdoc.exe"),
    }


def attach(ctx: OperationContext, force: bool, confirm_vulkan: bool, vm_index: str = "") -> str:
    cfg = ctx.cfg()
    ensure_mumu_root(cfg)
    if vm_index:
        cfg.emulator.vm_index = vm_index
    service = CaptureService(cfg, capture_bridge_client(cfg, start_qrenderdoc=True), MuMu12(cfg))
    launch_id = service.attach(force=force, confirm_vulkan=confirm_vulkan)
    cfg.capture.active_launch_id = launch_id
    return launch_id


def capture(ctx: OperationContext, output_dir: str | Path, timeout_seconds: int) -> Path:
    cfg = ctx.cfg()
    service = CaptureService(cfg, capture_bridge_client(cfg, start_qrenderdoc=False), MuMu12(cfg))
    return service.capture(output_dir, timeout_seconds=timeout_seconds)


def export_assets(ctx: OperationContext, rdc_path: str | Path, output_dir: str | Path, assets: str) -> dict:
    cfg = ctx.cfg()
    return ExportService(mcp_client(cfg)).export(rdc_path, output_dir, assets)


def release_session(ctx: OperationContext) -> None:
    cfg = ctx.cfg()
    cfg.capture.active_session_id = None
    cfg.capture.active_launch_id = ""
    cfg.capture.active_pid = None
    cfg.capture.active_session_started_at = None


def start_mcp(ctx: OperationContext) -> FileIpcMcpClient:
    return mcp_client(ctx.cfg())


def stop_mcp(ctx: OperationContext) -> None:
    cfg = ctx.cfg()
    executable_path = cfg.mcp.executable_path or "RenderDocMCP.exe"
    stop_standalone_mcp_bridge(executable_path)
    if is_process_running("qrenderdoc.exe"):
        terminate_process_tree("qrenderdoc.exe")
        _wait_for_process_exit("qrenderdoc.exe", timeout_seconds=5.0)
    release_session(ctx)


def restart_mcp(ctx: OperationContext) -> FileIpcMcpClient:
    stop_mcp(ctx)
    return start_mcp(ctx)


def mcp_client(cfg: AppConfig, require_capture_connect: bool = False) -> FileIpcMcpClient:
    if not RenderDocInstaller(cfg).ensure_installed():
        raise DependencyMissing("RenderDoc v1.44 was not found. Run rdc-auto setup before this command.")
    mcp_exe = McpInstaller(cfg).runtime_executable()
    cfg.mcp.executable_path = str(mcp_exe)
    qrenderdoc_running = is_process_running("qrenderdoc.exe")
    if cfg.mcp.extension_patch_restart_required:
        if qrenderdoc_running:
            raise UserActionRequired(
                "RenderDocMCP was updated to auto-connect MuMuVMHeadless. Close all RenderDoc windows, then rerun the command."
            )
        cfg.mcp.extension_patch_restart_required = False

    patch_applied = patch_renderdoc_mcp_extension(mcp_exe)
    if patch_applied:
        cfg.mcp.extension_patch_restart_required = qrenderdoc_running
        if qrenderdoc_running:
            raise UserActionRequired(
                "RenderDocMCP was updated to auto-connect MuMuVMHeadless. Close all RenderDoc windows, then rerun the command."
            )

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
        raise DependencyMissing("RenderDoc v1.44 was not found. Run rdc-auto setup before this command.")

    bridge_installer = CaptureBridgeInstaller()
    bridge_installer.install()
    running_count = count_processes("qrenderdoc.exe")
    if running_count > 1:
        raise UserActionRequired(
            "Multiple qrenderdoc.exe instances are running. Close extra RenderDoc windows and rerun the command."
        )

    if running_count == 0:
        if not start_qrenderdoc:
            raise UserActionRequired("No qrenderdoc.exe is running. Run rdc-auto attach first.")
        start_qrenderdoc_process(cfg, python_script=bridge_installer.bootstrap_script())
        already_running = False
    else:
        already_running = True

    client = CaptureBridgeClient()
    try:
        wait_for_capture_bridge(client)
    except DependencyMissing as exc:
        if already_running:
            raise UserActionRequired(
                "The running RenderDoc window has not loaded the rdc-auto capture bridge. "
                "Close all RenderDoc windows, then rerun rdc-auto attach."
            ) from exc
        raise
    return client


def start_qrenderdoc(cfg: AppConfig) -> None:
    start_qrenderdoc_process(cfg)


def start_qrenderdoc_process(cfg: AppConfig, python_script: Path | None = None) -> None:
    qrenderdoc = Path(cfg.renderdoc.qrenderdoc_path)
    if not qrenderdoc.is_file():
        raise DependencyMissing(f"qrenderdoc.exe was not found: {qrenderdoc}")
    if python_script is not None:
        python_script = Path(python_script)
        if not python_script.is_file():
            raise DependencyMissing(f"qrenderdoc Python bootstrap was not found: {python_script}")
    running_count = count_processes("qrenderdoc.exe")
    if running_count > 1:
        raise UserActionRequired(
            "Multiple qrenderdoc.exe instances are running. Close extra RenderDoc windows and rerun the command."
        )
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
    if not sys.platform.startswith("win"):
        return

    names = {"renderdoc-mcp.exe", "RenderDocMCP.exe"}
    name = executable_name(executable_path)
    if name:
        names.add(name)

    for image_name in sorted(names, key=str.lower):
        if image_name.lower() == "qrenderdoc.exe":
            continue
        if count_processes(image_name) == 0:
            continue
        terminate_process_tree(image_name)
        _wait_for_process_exit(image_name, timeout_seconds=5.0)


def wait_for_mcp(client: FileIpcMcpClient, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if client.ping():
                return
            last_error = RdcAutoError("RenderDocMCP ping returned an unexpected response")
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
            last_error = RdcAutoError("rdc-auto capture bridge ping returned an unexpected response")
        except (FileNotFoundError, TimeoutError, RdcAutoError) as exc:
            last_error = exc
        time.sleep(0.25)
    detail = f": {last_error}" if last_error else ""
    raise DependencyMissing(f"rdc-auto capture bridge did not become ready within {int(timeout_seconds)} seconds{detail}")


def ensure_capture_connect_capability(client: FileIpcMcpClient) -> None:
    try:
        client.call("list_running_targets", timeout=5.0)
    except McpCapabilityMissing as exc:
        raise UserActionRequired(
            "RenderDocMCP in the currently running RenderDoc window is still using an older extension. "
            "Close all RenderDoc windows, then rerun rdc-auto capture."
        ) from exc


def ensure_mumu_root(cfg: AppConfig) -> Path:
    if cfg.emulator.root_dir:
        try:
            root = canonical_mumu_root(cfg.emulator.root_dir, cfg.emulator.exe_relative_path)
            cfg.emulator.root_dir = str(root)
            return validate_mumu_root(root, cfg.emulator.exe_relative_path)
        except FileNotFoundError:
            cfg.emulator.root_dir = ""

    root = prompt_path("MuMu12 root directory")
    canonical_root = canonical_mumu_root(root, cfg.emulator.exe_relative_path)
    exe = validate_mumu_root(canonical_root, cfg.emulator.exe_relative_path)
    cfg.emulator.root_dir = str(canonical_root)
    return exe


def _wait_for_process_exit(image_name: str, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if count_processes(image_name) == 0:
            return
        time.sleep(0.1)
    raise RdcAutoError(f"Timed out waiting for stale RenderDocMCP bridge process to exit: {image_name}")
