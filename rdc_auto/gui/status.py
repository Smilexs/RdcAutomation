from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from rdc_auto.config import AppConfig
from rdc_auto.errors import McpCapabilityMissing, RdcAutoError
from rdc_auto.mcp_client import FileIpcMcpClient
from rdc_auto.paths import validate_mumu_root
from rdc_auto.processes import count_processes
from rdc_auto.renderdoc_installer import RENDERDOC_VERSION


@dataclass(frozen=True)
class McpRuntimeProbe:
    process_running: bool
    reachable: bool
    detail: str = ""


def probe_mcp_runtime(process_counts: dict[str, int] | None = None, ping_timeout: float = 0.75) -> McpRuntimeProbe:
    def process_count(name: str) -> int:
        if process_counts is not None:
            return process_counts.get(name, 0)
        return count_processes(name)

    qrenderdoc_count = process_count("qrenderdoc.exe")
    standalone_count = process_count("RenderDocMCP.exe") + process_count("renderdoc-mcp.exe")
    process_running = qrenderdoc_count == 1 or standalone_count > 0
    if qrenderdoc_count > 1:
        return McpRuntimeProbe(True, False, "multiple qrenderdoc.exe instances are running")
    if not process_running:
        return McpRuntimeProbe(False, False, "MCP process is not running")

    client = FileIpcMcpClient(
        executable_path=None,
        process_alive=lambda: (
            count_processes("qrenderdoc.exe") == 1
            or count_processes("RenderDocMCP.exe") > 0
            or count_processes("renderdoc-mcp.exe") > 0
        ),
        process_description="RenderDoc MCP runtime",
    )
    try:
        result = client.call("ping", timeout=ping_timeout)
    except McpCapabilityMissing as exc:
        return McpRuntimeProbe(True, False, str(exc))
    except (FileNotFoundError, TimeoutError, RdcAutoError, OSError, ValueError) as exc:
        return McpRuntimeProbe(True, False, str(exc))
    reachable = result.get("status") == "ok"
    return McpRuntimeProbe(True, reachable, "ok" if reachable else "unexpected ping response")


def build_status_snapshot(
    cfg: AppConfig,
    process_counts: dict[str, int] | None = None,
    mcp_runtime: McpRuntimeProbe | None = None,
) -> dict:
    def process_count(name: str) -> int:
        if process_counts is not None:
            return process_counts.get(name, 0)
        return count_processes(name)

    renderdoc_ready, renderdoc_invalid_reason = _renderdoc_status(cfg)
    mcp_ready, mcp_invalid_reason = _mcp_config_status(cfg)
    mcp_process_running = (
        process_count("qrenderdoc.exe") == 1
        or process_count("RenderDocMCP.exe") > 0
        or process_count("renderdoc-mcp.exe") > 0
    )
    if mcp_runtime is None:
        mcp_running = mcp_process_running
        mcp_runtime_detail = "not probed"
    else:
        mcp_running = mcp_runtime.reachable
        mcp_runtime_detail = mcp_runtime.detail
    session_attached = bool(cfg.capture.active_session_id or cfg.capture.active_launch_id)
    config_preview = asdict(cfg)
    if config_preview.get("ai", {}).get("api_key"):
        config_preview["ai"]["api_key"] = "********"
    mumu_ready, mumu_invalid_reason = _mumu_status(cfg)

    return {
        "renderdoc": {
            "ready": renderdoc_ready,
            "version": cfg.renderdoc.version or RENDERDOC_VERSION,
            "path": cfg.renderdoc.qrenderdoc_path,
            "invalid_reason": renderdoc_invalid_reason,
        },
        "mumu": {
            "ready": mumu_ready,
            "root_dir": cfg.emulator.root_dir,
            "vm_index": cfg.emulator.vm_index,
            "graphics_api": cfg.emulator.graphics_api,
            "invalid_reason": mumu_invalid_reason,
        },
        "mcp": {
            "ready": mcp_ready,
            "running": mcp_running,
            "process_running": mcp_runtime.process_running if mcp_runtime is not None else mcp_process_running,
            "runtime_detail": mcp_runtime_detail,
            "version": _mcp_display_version(cfg),
            "path": cfg.mcp.executable_path,
            "invalid_reason": mcp_invalid_reason,
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


def _renderdoc_status(cfg: AppConfig) -> tuple[bool, str]:
    raw_path = cfg.renderdoc.qrenderdoc_path.strip()
    if not raw_path:
        return False, "qrenderdoc.exe path is not configured"
    path = Path(raw_path)
    if path.name.lower() != "qrenderdoc.exe":
        return False, f"qrenderdoc.exe path must point to qrenderdoc.exe: {path}"
    if not path.is_file():
        return False, f"qrenderdoc.exe was not found: {path}"
    return True, ""


def _mcp_config_status(cfg: AppConfig) -> tuple[bool, str]:
    raw_path = cfg.mcp.executable_path.strip()
    if not raw_path:
        return False, "RenderDocMCP path is not configured"
    path = Path(raw_path)
    if path.name.lower() not in {"renderdocmcp.exe", "renderdoc-mcp.exe"}:
        return False, f"RenderDocMCP path must point to RenderDocMCP.exe: {path}"
    if not path.is_file():
        return False, f"RenderDocMCP executable was not found: {path}"
    return True, ""


def _mumu_status(cfg: AppConfig) -> tuple[bool, str]:
    if not cfg.emulator.root_dir:
        return False, "MuMu12 root directory is not configured"
    try:
        validate_mumu_root(cfg.emulator.root_dir, cfg.emulator.exe_relative_path)
    except FileNotFoundError as exc:
        return False, str(exc)
    return True, ""


def _mcp_display_version(cfg: AppConfig) -> str:
    if cfg.mcp.release_tag:
        return cfg.mcp.release_tag
    if cfg.mcp.asset_name:
        return cfg.mcp.asset_name
    if cfg.mcp.executable_path:
        return "版本未记录"
    return "未配置"
