from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Protocol

from .config import AppConfig
from .emulator import MuMu12
from .errors import UserActionRequired


LAUNCH_TIMEOUT_SECONDS = 60.0


class McpCaller(Protocol):
    def call(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        raise NotImplementedError


class CaptureService:
    def __init__(self, config: AppConfig, mcp: McpCaller, mumu: MuMu12):
        self.config = config
        self.mcp = mcp
        self.mumu = mumu

    def attach(self, force: bool = False, confirm_vulkan: bool = False) -> str:
        spec = self._launch_spec()
        if not confirm_vulkan:
            raise UserActionRequired("Confirm MuMu12 is configured to use Vulkan before attach.")
        if self.mumu.is_running():
            if not force:
                raise UserActionRequired("MuMu12 is already running. Close it before attach or rerun with --force.")
            self.mumu.terminate()

        params = {
            "exe_path": str(spec["exe_path"]),
            "working_dir": str(spec["working_dir"]),
            "cmd_line": str(spec["cmd_line"]),
            "graphics_api": "vulkan",
            "connect_target": False,
        }

        result = self.mcp.call(
            "launch_application",
            params,
            timeout=LAUNCH_TIMEOUT_SECONDS + 60.0,
        )
        self._wait_for_emulator_process()
        self._clear_active_session()
        return str(result.get("launch_id") or result.get("ident") or result.get("pid") or result.get("session_id") or "")

    def _launch_spec(self) -> dict[str, Path | str]:
        launch_spec = getattr(self.mumu, "launch_spec", None)
        if launch_spec is not None:
            return launch_spec()
        exe = self.mumu.executable()
        return {"exe_path": exe, "working_dir": exe.parent, "cmd_line": ""}

    def _target_process_name(self) -> str:
        target_process_name = getattr(self.mumu, "target_process_name", None)
        if target_process_name is not None:
            return str(target_process_name()).strip()
        return ""

    def _wait_for_emulator_process(self) -> None:
        wait_until_running = getattr(self.mumu, "wait_until_running", None)
        if wait_until_running is None:
            return
        wait_until_running(LAUNCH_TIMEOUT_SECONDS)

    def capture(self, output_dir: str | Path, timeout_seconds: int = 60) -> Path:
        session_id = self._ensure_capture_session(timeout_seconds)

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

    def _ensure_capture_session(self, timeout_seconds: int) -> str:
        session_id = self.config.capture.active_session_id
        if session_id:
            status = self.mcp.call("get_target_status", {"session_id": session_id}, timeout=10.0)
            if _is_capture_capable_status(status):
                return session_id
            self._clear_active_session()

        target_process_name = self._target_process_name()
        result = self.mcp.call(
            "connect_running_target",
            {
                "target_process_name": target_process_name,
                "graphics_api": "vulkan",
                "timeout_seconds": max(5, int(timeout_seconds)),
            },
            timeout=max(10.0, float(timeout_seconds) + 5.0),
        )
        session_id = str(result.get("session_id") or "")
        if not session_id:
            raise UserActionRequired(
                f"RenderDoc did not return a target session for {target_process_name}. Run rdc-auto attach, wait for MuMu12 to finish starting, then rerun capture."
            )
        self.config.capture.active_session_id = session_id
        self.config.capture.active_pid = int(result.get("pid", 0) or 0)
        self.config.capture.active_session_started_at = dt.datetime.now().astimezone().isoformat()
        return session_id

    def close(self, terminate_process: bool = False) -> None:
        session_id = self.config.capture.active_session_id
        if not session_id:
            return
        try:
            self.mcp.call(
                "close_target",
                {"session_id": session_id, "terminate_process": terminate_process},
                timeout=10.0,
            )
        finally:
            self._clear_active_session()

    def _clear_active_session(self) -> None:
        self.config.capture.active_session_id = None
        self.config.capture.active_pid = None
        self.config.capture.active_session_started_at = None


def _is_capture_capable_status(status: dict) -> bool:
    if not status:
        return False

    if "alive" in status or "can_capture" in status:
        return bool(status.get("alive")) and bool(status.get("connected")) and bool(status.get("can_capture"))

    if status.get("exists") is False:
        return False

    state = str(status.get("status", "")).lower()
    if state in {"not_found", "disconnected", "closed", "close_error"}:
        return False

    connected = status.get("connected")
    controllable = status.get("controllable")
    if connected is False or controllable is False:
        return False
    return bool(connected or controllable)
