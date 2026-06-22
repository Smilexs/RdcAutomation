from __future__ import annotations

from dataclasses import asdict

from rdc_auto.config import AppConfig
from rdc_auto.processes import count_processes
from rdc_auto.renderdoc_installer import RENDERDOC_VERSION


def build_status_snapshot(cfg: AppConfig, process_counts: dict[str, int] | None = None) -> dict:
    def process_count(name: str) -> int:
        if process_counts is not None:
            return process_counts.get(name, 0)
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
