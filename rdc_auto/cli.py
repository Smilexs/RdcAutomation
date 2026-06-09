from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path

from .capture import CaptureService
from .config import load_config, save_config
from .emulator import MuMu12
from .errors import DependencyMissing, McpCapabilityMissing, RdcAutoError, UserActionRequired
from .export_assets import ExportService
from .log_setup import configure_logging
from .mcp_client import FileIpcMcpClient
from .mcp_installer import McpInstaller
from .paths import validate_mumu_root
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
    cfg = None

    try:
        cfg = load_config()
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


def _cmd_attach(cfg, force: bool, yes_vulkan: bool) -> None:
    _ensure_mumu_root(cfg)
    if not yes_vulkan:
        answer = choose_option("Confirm MuMu12 graphics API", ["vulkan", "stop"], default="vulkan")
        if answer != "vulkan":
            raise UserActionRequired("Set MuMu12 graphics API to Vulkan before attach.")

    service = CaptureService(cfg, _mcp_client(cfg), MuMu12(cfg))
    session_id = service.attach(force=force, confirm_vulkan=True)
    print(f"attached session: {session_id}")


def _cmd_capture(cfg, args) -> None:
    if not cfg.capture.active_session_id:
        answer = choose_option("No active RenderDoc target session", ["attach", "stop"], default="attach")
        if answer != "attach":
            raise UserActionRequired("No active RenderDoc target session. Run rdc-auto attach first.")
        _cmd_attach(cfg, force=False, yes_vulkan=False)

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
    if not RenderDocInstaller(cfg).ensure_installed():
        raise DependencyMissing("RenderDoc v1.44 was not found. Run rdc-auto setup before this command.")
    cfg.mcp.executable_path = str(McpInstaller(cfg).runtime_executable())
    _start_qrenderdoc(cfg)
    client = FileIpcMcpClient(executable_path=cfg.mcp.executable_path)
    _wait_for_mcp(client)
    return client


def _ensure_mumu_root(cfg) -> Path:
    if cfg.emulator.root_dir:
        try:
            return validate_mumu_root(cfg.emulator.root_dir)
        except FileNotFoundError:
            cfg.emulator.root_dir = ""

    root = prompt_path("MuMu12 root directory")
    exe = validate_mumu_root(root)
    cfg.emulator.root_dir = str(root)
    return exe


def _start_qrenderdoc(cfg) -> None:
    qrenderdoc = Path(cfg.renderdoc.qrenderdoc_path)
    if not qrenderdoc.is_file():
        raise DependencyMissing(f"qrenderdoc.exe was not found: {qrenderdoc}")
    if _process_is_running("qrenderdoc.exe"):
        return
    kwargs = {"cwd": str(qrenderdoc.parent), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(qrenderdoc)], **kwargs)


def _process_is_running(image_name: str) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    rows = csv.DictReader(StringIO(result.stdout))
    return any(row.get("Image Name", "").lower() == image_name.lower() for row in rows)


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
