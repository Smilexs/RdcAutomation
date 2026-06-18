from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path

from .capture_bridge import CaptureBridgeClient, CaptureBridgeInstaller
from .capture import CaptureService
from .config import load_config, save_config
from .emulator import MuMu12
from .errors import DependencyMissing, McpCapabilityMissing, RdcAutoError, UserActionRequired
from .export_assets import ExportService
from .log_setup import configure_logging
from .mcp_client import FileIpcMcpClient
from .mcp_installer import McpInstaller
from .mcp_patch import patch_renderdoc_mcp_extension
from .paths import canonical_mumu_root, validate_mumu_root
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
    attach.add_argument("--vm-index")

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
    cfg = None

    try:
        cfg = load_config()
        if args.command == "setup":
            _cmd_setup(cfg)
        elif args.command == "attach":
            _cmd_attach(cfg, force=args.force, yes_vulkan=args.yes_vulkan, vm_index=args.vm_index)
        elif args.command == "capture":
            _cmd_capture(cfg, args)
        elif args.command == "export":
            _cmd_export(cfg, args)
        save_config(cfg)
        return 0
    except UserActionRequired as exc:
        if cfg is not None:
            save_config(cfg)
        print(str(exc), file=sys.stderr)
        return 2
    except RdcAutoError as exc:
        if cfg is not None:
            save_config(cfg)
        print(str(exc), file=sys.stderr)
        return 1
    except (FileNotFoundError, TimeoutError) as exc:
        if cfg is not None:
            save_config(cfg)
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        if cfg is not None:
            save_config(cfg)
        print(f"Command failed with exit code {exc.returncode}: {' '.join(map(str, exc.cmd))}", file=sys.stderr)
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
        if not installer.ensure_installed():
            raise DependencyMissing("RenderDoc v1.44 installation completed, but qrenderdoc.exe with version 1.44 was not found.")

    _ensure_mumu_root(cfg)

    mcp = McpInstaller(cfg)
    mcp_exe = mcp.ensure_installed()
    cfg.mcp.executable_path = str(mcp_exe)
    print("setup complete")


def _cmd_attach(cfg, force: bool, yes_vulkan: bool, vm_index: str | None = None) -> None:
    _ensure_mumu_root(cfg)
    if vm_index is not None:
        cfg.emulator.vm_index = vm_index
    if not yes_vulkan:
        answer = choose_option("Confirm MuMu12 graphics API", ["vulkan", "stop"], default="vulkan")
        if answer != "vulkan":
            raise UserActionRequired("Set MuMu12 graphics API to Vulkan before attach.")

    service = CaptureService(cfg, _capture_bridge_client(cfg, start_qrenderdoc=True), MuMu12(cfg))
    launch_id = service.attach(force=force, confirm_vulkan=True)
    print(f"launched emulator: {launch_id}")


def _cmd_capture(cfg, args) -> None:
    out = Path(args.out) if args.out else prompt_path("Capture output directory", cfg.capture.last_output_dir or None)
    service = CaptureService(cfg, _capture_bridge_client(cfg, start_qrenderdoc=False), MuMu12(cfg))
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


def _mcp_client(cfg, require_capture_connect: bool = False) -> FileIpcMcpClient:
    if not RenderDocInstaller(cfg).ensure_installed():
        raise DependencyMissing("RenderDoc v1.44 was not found. Run rdc-auto setup before this command.")
    mcp_exe = McpInstaller(cfg).runtime_executable()
    cfg.mcp.executable_path = str(mcp_exe)
    qrenderdoc_running = _process_is_running("qrenderdoc.exe")
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

    _stop_standalone_mcp_bridge(mcp_exe)
    _start_qrenderdoc(cfg)
    client = FileIpcMcpClient(
        executable_path=None,
        process_alive=lambda: _process_count("qrenderdoc.exe") == 1,
        process_description="qrenderdoc.exe",
    )
    _wait_for_mcp(client)
    if require_capture_connect:
        _ensure_capture_connect_capability(client)
    return client


def _capture_bridge_client(cfg, start_qrenderdoc: bool) -> CaptureBridgeClient:
    if not RenderDocInstaller(cfg).ensure_installed():
        raise DependencyMissing("RenderDoc v1.44 was not found. Run rdc-auto setup before this command.")

    bridge_installer = CaptureBridgeInstaller()
    bridge_installer.install()
    running_count = _process_count("qrenderdoc.exe")
    if running_count > 1:
        raise UserActionRequired(
            "Multiple qrenderdoc.exe instances are running. Close extra RenderDoc windows and rerun the command."
        )

    if running_count == 0:
        if not start_qrenderdoc:
            raise UserActionRequired("No qrenderdoc.exe is running. Run rdc-auto attach first.")
        _start_qrenderdoc(cfg, python_script=bridge_installer.bootstrap_script())
        already_running = False
    else:
        already_running = True

    client = CaptureBridgeClient()
    try:
        _wait_for_capture_bridge(client)
    except DependencyMissing as exc:
        if already_running:
            raise UserActionRequired(
                "The running RenderDoc window has not loaded the rdc-auto capture bridge. "
                "Close all RenderDoc windows, then rerun rdc-auto attach."
            ) from exc
        raise
    return client


def _ensure_mumu_root(cfg) -> Path:
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


def _start_qrenderdoc(cfg, python_script: Path | None = None) -> None:
    qrenderdoc = Path(cfg.renderdoc.qrenderdoc_path)
    if not qrenderdoc.is_file():
        raise DependencyMissing(f"qrenderdoc.exe was not found: {qrenderdoc}")
    if python_script is not None:
        python_script = Path(python_script)
        if not python_script.is_file():
            raise DependencyMissing(f"qrenderdoc Python bootstrap was not found: {python_script}")
    running_count = _process_count("qrenderdoc.exe")
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


def _stop_standalone_mcp_bridge(executable_path: str | Path) -> None:
    if not sys.platform.startswith("win"):
        return

    names = {"renderdoc-mcp.exe", "RenderDocMCP.exe"}
    executable_name = Path(executable_path).name
    if executable_name:
        names.add(executable_name)

    for image_name in sorted(names, key=str.lower):
        if image_name.lower() == "qrenderdoc.exe":
            continue
        if _process_count(image_name) == 0:
            continue
        _terminate_process_tree(image_name)
        _wait_for_process_exit(image_name, timeout_seconds=5.0)


def _terminate_process_tree(image_name: str) -> None:
    try:
        result = subprocess.run(
            ["taskkill", "/IM", image_name, "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    if result.returncode != 0 and _process_count(image_name) > 0:
        details = "\n".join(part for part in [result.stderr, result.stdout] if part).strip()
        raise RdcAutoError(f"Failed to stop stale RenderDocMCP bridge process {image_name}: {details}")


def _wait_for_process_exit(image_name: str, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _process_count(image_name) == 0:
            return
        time.sleep(0.1)
    raise RdcAutoError(f"Timed out waiting for stale RenderDocMCP bridge process to exit: {image_name}")


def _process_is_running(image_name: str) -> bool:
    return _process_count(image_name) > 0


def _process_count(image_name: str) -> int:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 0
    return _count_tasklist_rows(result.stdout, image_name)


def _count_tasklist_rows(stdout: str, image_name: str) -> int:
    target = image_name.lower()
    rows = csv.reader(StringIO(stdout))
    count = 0
    for row in rows:
        if not row:
            continue
        if row[0].strip().lower() == target:
            count += 1
    return count


def _wait_for_mcp(client: FileIpcMcpClient, timeout_seconds: float = 30.0) -> None:
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


def _wait_for_capture_bridge(client: CaptureBridgeClient, timeout_seconds: float = 30.0) -> None:
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


def _ensure_capture_connect_capability(client: FileIpcMcpClient) -> None:
    try:
        client.call("list_running_targets", timeout=5.0)
    except McpCapabilityMissing as exc:
        raise UserActionRequired(
            "RenderDocMCP in the currently running RenderDoc window is still using an older extension. "
            "Close all RenderDoc windows, then rerun rdc-auto capture."
        ) from exc
