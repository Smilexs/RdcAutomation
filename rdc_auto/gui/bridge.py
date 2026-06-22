from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rdc_auto.config import load_config, save_config
from rdc_auto.errors import UserActionRequired
from rdc_auto.export_assets import ExportService
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
    mcp_client,
    start_mcp,
    stop_mcp,
)


EmitProgress = Callable[[str, int], None]
JobFn = Callable[[EmitProgress], dict[str, Any]]


class GuiBridge:
    def __init__(self, run_jobs_inline: bool = False):
        self.window = None
        self.jobs = JobManager(run_inline=run_jobs_inline)

    def bind_window(self, window) -> None:
        self.window = window

    def get_status(self, payload: dict | None = None) -> dict:
        try:
            return self._ok(build_status_snapshot(load_config()))
        except Exception as exc:
            return self._fail(exc)

    def save_environment(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            cfg = load_config()
            cfg.renderdoc.qrenderdoc_path = str(payload.get("renderdoc_path", "")).strip()
            cfg.emulator.root_dir = str(payload.get("mumu_root", "")).strip()
            cfg.emulator.vm_index = str(payload.get("vm_index", "")).strip()
            cfg.emulator.graphics_api = str(payload.get("graphics_api", "vulkan")).strip() or "vulkan"
            save_config(cfg)
            return self._ok(build_status_snapshot(cfg), logs=["environment config saved"])
        except Exception as exc:
            return self._fail(exc)

    def save_mcp(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            cfg = load_config()
            cfg.mcp.executable_path = str(payload.get("executable_path", payload.get("mcp_path", ""))).strip()
            save_config(cfg)
            return self._ok(build_status_snapshot(cfg), logs=["MCP config saved"])
        except Exception as exc:
            return self._fail(exc)

    def save_ai(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            cfg = load_config()
            cfg.ai.provider = str(payload.get("provider", "openai")).strip() or "openai"
            cfg.ai.model = str(payload.get("model", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
            cfg.ai.base_url = str(payload.get("base_url", "https://api.openai.com/v1")).strip() or "https://api.openai.com/v1"
            cfg.ai.api_key = ""
            save_config(cfg)
            return self._ok(build_status_snapshot(cfg), logs=["AI settings saved without persisting API key"])
        except Exception as exc:
            return self._fail(exc)

    def test_ai(self, payload: dict | None = None) -> dict:
        try:
            return self._ok({"connected": True, "mode": "frontend-only"}, logs=["AI test uses local GUI mode"])
        except Exception as exc:
            return self._fail(exc)

    def send_chat(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            message = str(payload.get("message", "")).strip()
            return self._ok({"reply": _local_ai_reply(message)}, logs=["AI local reply generated"])
        except Exception as exc:
            return self._fail(exc)

    def start_job(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            action = str(payload.get("action", "")).strip()
            raw_params = payload.get("params", {})
            params = raw_params if isinstance(raw_params, dict) else {}

            actions: dict[str, JobFn] = {
                "check_environment": lambda emit: check_environment(OperationContext(progress=emit)),
                "setup": lambda emit: _completed(setup_environment(OperationContext(progress=emit))),
                "start_mcp": lambda emit: _running(start_mcp(OperationContext(progress=emit))),
                "stop_mcp": lambda emit: _stopped(stop_mcp(OperationContext(progress=emit))),
                "restart_mcp": lambda emit: _running(restart_mcp(OperationContext(progress=emit))),
                "attach": lambda emit: {
                    "launch_id": str(
                        attach(
                            OperationContext(progress=emit),
                            force=_payload_bool(params.get("force")),
                            confirm_vulkan=_payload_bool(params.get("confirm_vulkan")),
                            vm_index=str(params.get("vm_index", "")),
                        )
                    )
                },
                "capture": lambda emit: {
                    "rdc_path": str(
                        capture(
                            OperationContext(progress=emit),
                            output_dir=str(params.get("output_dir", "")),
                            timeout_seconds=int(params.get("timeout_seconds", 60)),
                        )
                    )
                },
                "export": lambda emit: _export_result(params, emit),
                "release_session": lambda emit: _released(release_session(OperationContext(progress=emit))),
            }
            fn = actions.get(action)
            if fn is None:
                return self._fail(ValueError(f"Unsupported GUI action: {action}"))
            return self._ok(self.jobs.start(action, fn))
        except Exception as exc:
            return self._fail(exc)

    def get_job(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            return self._ok(self.jobs.get(str(payload.get("job_id", ""))))
        except Exception as exc:
            return self._fail(exc)

    def load_eid_list(self, payload: dict | None = None) -> dict:
        try:
            payload = payload or {}
            rdc_path = str(payload.get("rdc_path", "")).strip()
            if not rdc_path:
                raise ValueError("rdc_path is required.")
            cfg = load_config()
            rows = ExportService(mcp_client(cfg)).list_draw_calls(rdc_path)
            return self._ok({"rows": rows}, logs=[f"loaded {len(rows)} EID rows"])
        except Exception as exc:
            return self._fail(exc)

    def export_eid_model(self, payload: dict | None = None) -> dict:
        try:
            payload = payload or {}
            rdc_path = str(payload.get("rdc_path", "")).strip()
            output_dir = str(payload.get("output_dir", "")).strip()
            event_id = int(payload.get("event_id"))
            if not rdc_path:
                raise ValueError("rdc_path is required.")
            if not output_dir:
                raise ValueError("output_dir is required.")
            result = ExportService(mcp_client(load_config())).export_mesh_for_event(rdc_path, output_dir, event_id)
            return self._ok(result, logs=[f"exported model for EID {event_id}"])
        except Exception as exc:
            return self._fail(exc)

    def export_eid_textures(self, payload: dict | None = None) -> dict:
        try:
            payload = payload or {}
            rdc_path = str(payload.get("rdc_path", "")).strip()
            output_dir = str(payload.get("output_dir", "")).strip()
            event_id = int(payload.get("event_id"))
            if not rdc_path:
                raise ValueError("rdc_path is required.")
            if not output_dir:
                raise ValueError("output_dir is required.")
            result = ExportService(mcp_client(load_config())).export_bound_textures_for_event(rdc_path, output_dir, event_id)
            texture_count = len(result.get("textures", []))
            return self._ok(result, logs=[f"exported {texture_count} textures for EID {event_id}"])
        except Exception as exc:
            return self._fail(exc)

    def choose_directory(self, payload: dict | None = None) -> dict:
        try:
            if self.window is None:
                return self._fail(UserActionRequired("The GUI window is not ready."))
            import webview

            payload = payload or {}
            result = self.window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=str(payload.get("initial_dir", "")),
            )
            return self._ok({"path": result[0] if result else ""})
        except Exception as exc:
            return self._fail(exc)

    def choose_file(self, payload: dict | None = None) -> dict:
        try:
            if self.window is None:
                return self._fail(UserActionRequired("The GUI window is not ready."))
            import webview

            result = self.window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("RenderDoc Capture (*.rdc)",),
            )
            return self._ok({"path": result[0] if result else ""})
        except Exception as exc:
            return self._fail(exc)

    def open_path(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            raw_path = str(payload.get("path", "")).strip()
            if not raw_path:
                return self._fail(ValueError("Path is required."))
            path = Path(raw_path)
            if not path.exists():
                return self._fail(FileNotFoundError(str(path)))
            os.startfile(str(path))
            return self._ok({"opened": str(path)})
        except Exception as exc:
            return self._fail(exc)

    @staticmethod
    def _ok(data, logs: list[str] | None = None) -> dict:
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


def _completed(result: Any) -> dict[str, bool]:
    return {"completed": True}


def _running(result: Any) -> dict[str, bool]:
    return {"running": True}


def _stopped(result: Any) -> dict[str, bool]:
    return {"running": False}


def _released(result: Any) -> dict[str, bool]:
    return {"released": True}


def _payload_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return False


def _export_result(params: dict, emit: EmitProgress) -> dict[str, Any]:
    output_dir = str(params.get("output_dir", ""))
    manifest = export_assets(
        OperationContext(progress=emit),
        rdc_path=str(params.get("rdc_path", "")),
        output_dir=output_dir,
        assets=str(params.get("assets", "both")),
    )
    return {"manifest": manifest, "output_dir": output_dir}


def _local_ai_reply(message: str) -> str:
    lower = message.lower()
    if "attach" in lower or "connect" in lower:
        return "Check that MuMu12 is using Vulkan, then close extra qrenderdoc.exe instances before attaching."
    if "mcp" in lower:
        return "Run the environment check first; if the extension needs a restart, close RenderDoc and retry."
    if "export" in lower:
        return "Confirm the RDC file exists, MCP is running, and the output directory is writable."
    return "Check the status bar and logs, then proceed in order: environment, attach, capture, export."
