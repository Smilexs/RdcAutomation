from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from . import operations as _operations
from . import processes as _processes
from .capture import CaptureService
from .capture_bridge import CaptureBridgeClient, CaptureBridgeInstaller
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


_NATIVE_OPERATION_HOOKS = {
    "capture_bridge_client": _operations.capture_bridge_client,
    "mcp_client": _operations.mcp_client,
    "start_qrenderdoc": _operations.start_qrenderdoc,
    "start_qrenderdoc_process": _operations.start_qrenderdoc_process,
    "stop_standalone_mcp_bridge": _operations.stop_standalone_mcp_bridge,
    "wait_for_capture_bridge": _operations.wait_for_capture_bridge,
    "wait_for_mcp": _operations.wait_for_mcp,
    "ensure_capture_connect_capability": _operations.ensure_capture_connect_capability,
}


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
    _sync_operations_hooks()
    _operations.setup_environment(_operations.OperationContext(config=cfg))
    print("setup complete")


def _cmd_attach(cfg, force: bool, yes_vulkan: bool, vm_index: str | None = None) -> None:
    if not yes_vulkan:
        answer = choose_option("Confirm MuMu12 graphics API", ["vulkan", "stop"], default="vulkan")
        if answer != "vulkan":
            raise UserActionRequired("Set MuMu12 graphics API to Vulkan before attach.")
    _sync_operations_hooks()
    launch_id = _operations.attach(
        _operations.OperationContext(config=cfg),
        force=force,
        confirm_vulkan=True,
        vm_index=vm_index or "",
    )
    print(f"launched emulator: {launch_id}")


def _cmd_capture(cfg, args) -> None:
    out = Path(args.out) if args.out else prompt_path("Capture output directory", cfg.capture.last_output_dir or None)
    _sync_operations_hooks()
    rdc_path = _operations.capture(_operations.OperationContext(config=cfg), out, timeout_seconds=args.timeout)
    print(f"captured: {rdc_path}")


def _cmd_export(cfg, args) -> None:
    rdc_path = Path(args.rdc_path) if args.rdc_path else prompt_path("RDC file", cfg.capture.last_rdc_path or None)
    assets = args.assets or choose_option("Export assets", ["textures", "meshes", "both"], default="both")
    out = Path(args.out) if args.out else prompt_path("Export output directory")
    _sync_operations_hooks()
    manifest = _operations.export_assets(_operations.OperationContext(config=cfg), rdc_path, out, assets)
    print(f"export complete: {out}")
    print(f"textures: {manifest['assets']['textures']['success']} ok, {manifest['assets']['textures']['failed']} failed")
    print(f"meshes: {manifest['assets']['meshes']['success']} ok, {manifest['assets']['meshes']['failed']} failed")


def _mcp_client(cfg, require_capture_connect: bool = False) -> FileIpcMcpClient:
    _sync_operations_hooks()
    return _operations.mcp_client(cfg, require_capture_connect=require_capture_connect)


def _capture_bridge_client(cfg, start_qrenderdoc: bool) -> CaptureBridgeClient:
    _sync_operations_hooks()
    return _operations.capture_bridge_client(cfg, start_qrenderdoc=start_qrenderdoc)


def _ensure_mumu_root(cfg) -> Path:
    _sync_operations_hooks()
    return _operations.ensure_mumu_root(cfg)


def _start_qrenderdoc(cfg, python_script: Path | None = None) -> None:
    _sync_operations_hooks()
    return _operations.start_qrenderdoc_process(cfg, python_script=python_script)


def _stop_standalone_mcp_bridge(executable_path: str | Path) -> None:
    _sync_operations_hooks()
    return _operations.stop_standalone_mcp_bridge(executable_path)


def _terminate_process_tree(image_name: str) -> None:
    return _processes.terminate_process_tree(image_name, runner=subprocess.run)


def _wait_for_process_exit(image_name: str, timeout_seconds: float) -> None:
    _sync_operations_hooks()
    return _operations._wait_for_process_exit(image_name, timeout_seconds)


def _process_is_running(image_name: str) -> bool:
    return _processes.is_process_running(image_name, runner=subprocess.run)


def _process_count(image_name: str) -> int:
    return _processes.count_processes(image_name, runner=subprocess.run)


def _count_tasklist_rows(stdout: str, image_name: str) -> int:
    return _processes.tasklist_count_from_csv(stdout, image_name)


def _wait_for_mcp(client: FileIpcMcpClient, timeout_seconds: float = 30.0) -> None:
    _sync_operations_hooks()
    return _operations.wait_for_mcp(client, timeout_seconds=timeout_seconds)


def _wait_for_capture_bridge(client: CaptureBridgeClient, timeout_seconds: float = 30.0) -> None:
    _sync_operations_hooks()
    return _operations.wait_for_capture_bridge(client, timeout_seconds=timeout_seconds)


def _ensure_capture_connect_capability(client: FileIpcMcpClient) -> None:
    _sync_operations_hooks()
    return _operations.ensure_capture_connect_capability(client)


def _sync_operations_hooks() -> None:
    _operations.RenderDocInstaller = RenderDocInstaller
    _operations.McpInstaller = McpInstaller
    _operations.CaptureService = CaptureService
    _operations.CaptureBridgeClient = CaptureBridgeClient
    _operations.CaptureBridgeInstaller = CaptureBridgeInstaller
    _operations.MuMu12 = MuMu12
    _operations.ExportService = ExportService
    _operations.FileIpcMcpClient = FileIpcMcpClient
    _operations.patch_renderdoc_mcp_extension = patch_renderdoc_mcp_extension
    _operations.canonical_mumu_root = canonical_mumu_root
    _operations.validate_mumu_root = validate_mumu_root
    _operations.prompt_path = prompt_path
    _operations.save_config = save_config
    _operations.count_processes = _process_count
    _operations.is_process_running = _process_is_running
    _operations.terminate_process_tree = _terminate_process_tree

    _operations.capture_bridge_client = (
        _capture_bridge_client
        if _capture_bridge_client is not _ORIGINAL_CAPTURE_BRIDGE_CLIENT
        else _NATIVE_OPERATION_HOOKS["capture_bridge_client"]
    )
    _operations.mcp_client = (
        _mcp_client if _mcp_client is not _ORIGINAL_MCP_CLIENT else _NATIVE_OPERATION_HOOKS["mcp_client"]
    )
    if _start_qrenderdoc is not _ORIGINAL_START_QRENDERDOC:
        _operations.start_qrenderdoc = _start_qrenderdoc
        _operations.start_qrenderdoc_process = _start_qrenderdoc
    else:
        _operations.start_qrenderdoc = _NATIVE_OPERATION_HOOKS["start_qrenderdoc"]
        _operations.start_qrenderdoc_process = _NATIVE_OPERATION_HOOKS["start_qrenderdoc_process"]
    _operations.stop_standalone_mcp_bridge = (
        _stop_standalone_mcp_bridge
        if _stop_standalone_mcp_bridge is not _ORIGINAL_STOP_STANDALONE_MCP_BRIDGE
        else _NATIVE_OPERATION_HOOKS["stop_standalone_mcp_bridge"]
    )
    _operations.wait_for_capture_bridge = (
        _wait_for_capture_bridge
        if _wait_for_capture_bridge is not _ORIGINAL_WAIT_FOR_CAPTURE_BRIDGE
        else _NATIVE_OPERATION_HOOKS["wait_for_capture_bridge"]
    )
    _operations.wait_for_mcp = (
        _wait_for_mcp if _wait_for_mcp is not _ORIGINAL_WAIT_FOR_MCP else _NATIVE_OPERATION_HOOKS["wait_for_mcp"]
    )
    _operations.ensure_capture_connect_capability = (
        _ensure_capture_connect_capability
        if _ensure_capture_connect_capability is not _ORIGINAL_ENSURE_CAPTURE_CONNECT_CAPABILITY
        else _NATIVE_OPERATION_HOOKS["ensure_capture_connect_capability"]
    )


_ORIGINAL_CAPTURE_BRIDGE_CLIENT = _capture_bridge_client
_ORIGINAL_MCP_CLIENT = _mcp_client
_ORIGINAL_START_QRENDERDOC = _start_qrenderdoc
_ORIGINAL_STOP_STANDALONE_MCP_BRIDGE = _stop_standalone_mcp_bridge
_ORIGINAL_WAIT_FOR_CAPTURE_BRIDGE = _wait_for_capture_bridge
_ORIGINAL_WAIT_FOR_MCP = _wait_for_mcp
_ORIGINAL_ENSURE_CAPTURE_CONNECT_CAPABILITY = _ensure_capture_connect_capability
