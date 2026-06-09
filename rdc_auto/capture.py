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
