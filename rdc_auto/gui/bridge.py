from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rdc_auto.config import load_config, save_config
from rdc_auto.errors import UserActionRequired
from rdc_auto.export_assets import ExportService, _parse_event_id
from rdc_auto.gui.jobs import JobManager
from rdc_auto.gui.status import build_status_snapshot, probe_mcp_runtime
from rdc_auto.paths import canonical_mumu_root
from rdc_auto.operations import (
    OperationContext,
    attach,
    capture,
    check_environment,
    export_assets,
    release_session,
    restart_mcp,
    setup_environment,
    setup_renderdoc,
    setup_renderdoc_and_mcp,
    setup_mcp,
    mcp_client,
    start_mcp,
    stop_mcp,
)
from rdc_auto.processes import process_ids, terminate_process_tree_by_pid


EmitProgress = Callable[[str, int], None]
JobFn = Callable[[EmitProgress], dict[str, Any]]
MCP_RUNTIME_IMAGES = ("qrenderdoc.exe", "RenderDocMCP.exe", "renderdoc-mcp.exe")


class GuiBridge:
    def __init__(self, run_jobs_inline: bool = False):
        self._window = None
        self.jobs = JobManager(run_inline=run_jobs_inline)
        self._owned_mcp_pids: dict[str, set[int]] = {image: set() for image in MCP_RUNTIME_IMAGES}

    def bind_window(self, window) -> None:
        self._window = window

    def get_status(self, payload: dict | None = None) -> dict:
        try:
            cfg = load_config()
            return self._ok(build_status_snapshot(cfg, mcp_runtime=probe_mcp_runtime()))
        except Exception as exc:
            return self._fail(exc)

    def save_environment(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            cfg = load_config()
            cfg.renderdoc.qrenderdoc_path = str(payload.get("renderdoc_path", "")).strip()
            cfg.mcp.executable_path = str(payload.get("executable_path", payload.get("mcp_path", ""))).strip()
            mumu_root = str(payload.get("mumu_root", "")).strip()
            if mumu_root:
                try:
                    cfg.emulator.root_dir = str(canonical_mumu_root(mumu_root, cfg.emulator.exe_relative_path))
                except FileNotFoundError:
                    cfg.emulator.root_dir = mumu_root
            else:
                cfg.emulator.root_dir = ""
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

    def save_capture_paths(self, payload: dict) -> dict:
        try:
            payload = payload or {}
            cfg = load_config()
            if "rdc_path" in payload:
                cfg.capture.last_rdc_path = str(payload.get("rdc_path", "")).strip()
            if "capture_output_dir" in payload:
                cfg.capture.last_output_dir = str(payload.get("capture_output_dir", "")).strip()
            if "export_output_dir" in payload:
                cfg.export.last_output_dir = str(payload.get("export_output_dir", "")).strip()
            if "output_dir" in payload:
                cfg.capture.last_output_dir = str(payload.get("output_dir", "")).strip()
            save_config(cfg)
            return self._ok(build_status_snapshot(cfg), logs=["capture paths saved"])
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
                "setup_renderdoc": lambda emit: _completed(setup_renderdoc(OperationContext(progress=emit))),
                "setup_renderdoc_mcp": lambda emit: _completed(setup_renderdoc_and_mcp(OperationContext(progress=emit))),
                "setup_mcp": lambda emit: _completed(setup_mcp(OperationContext(progress=emit))),
                "start_mcp": lambda emit: _running(
                    self._track_mcp_runtime_start(lambda: start_mcp(OperationContext(progress=emit)))
                ),
                "stop_mcp": lambda emit: _stopped(self._stop_mcp_from_gui(OperationContext(progress=emit))),
                "restart_mcp": lambda emit: _running(
                    self._track_mcp_runtime_start(
                        lambda: restart_mcp(OperationContext(progress=emit), force_release_session=True)
                    )
                ),
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
                "export": lambda emit: self._track_mcp_runtime_start(lambda: _export_result(params, emit)),
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
            rows = self._track_mcp_runtime_start(lambda: ExportService(mcp_client(cfg)).list_draw_calls(rdc_path))
            return self._ok({"rows": rows}, logs=[f"loaded {len(rows)} EID rows"])
        except Exception as exc:
            return self._fail(exc)

    def export_eid_model(self, payload: dict | None = None) -> dict:
        try:
            payload = payload or {}
            rdc_path = str(payload.get("rdc_path", "")).strip()
            output_dir = str(payload.get("output_dir", "")).strip()
            event_id = _parse_event_id(payload.get("event_id"))
            if not rdc_path:
                raise ValueError("rdc_path is required.")
            if not output_dir:
                raise ValueError("output_dir is required.")
            result = self._track_mcp_runtime_start(
                lambda: ExportService(mcp_client(load_config())).export_mesh_for_event(rdc_path, output_dir, event_id)
            )
            return self._ok(result, logs=[f"exported model for EID {event_id}"])
        except Exception as exc:
            return self._fail(exc)

    def export_eid_textures(self, payload: dict | None = None) -> dict:
        try:
            payload = payload or {}
            rdc_path = str(payload.get("rdc_path", "")).strip()
            output_dir = str(payload.get("output_dir", "")).strip()
            event_id = _parse_event_id(payload.get("event_id"))
            if not rdc_path:
                raise ValueError("rdc_path is required.")
            if not output_dir:
                raise ValueError("output_dir is required.")
            result = self._track_mcp_runtime_start(
                lambda: ExportService(mcp_client(load_config())).export_bound_textures_for_event(
                    rdc_path, output_dir, event_id
                )
            )
            texture_count = len(result.get("textures", []))
            return self._ok(result, logs=[f"exported {texture_count} textures for EID {event_id}"])
        except Exception as exc:
            return self._fail(exc)

    def choose_directory(self, payload: dict | None = None) -> dict:
        try:
            if self._window is None:
                return self._fail(UserActionRequired("The GUI window is not ready."))
            import webview

            payload = payload or {}
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=str(payload.get("initial_dir", "")),
            )
            return self._ok({"path": result[0] if result else ""})
        except Exception as exc:
            return self._fail(exc)

    def choose_file(self, payload: dict | None = None) -> dict:
        try:
            if self._window is None:
                return self._fail(UserActionRequired("The GUI window is not ready."))
            import webview

            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("RenderDoc Capture (*.rdc)",),
            )
            return self._ok({"path": result[0] if result else ""})
        except Exception as exc:
            return self._fail(exc)

    def list_rdc_files(self, payload: dict | None = None) -> dict:
        try:
            payload = payload or {}
            raw_directory = str(payload.get("directory", "")).strip()
            if not raw_directory:
                files: list[Path] = []
            else:
                directory = Path(raw_directory)
                if not directory.exists() or not directory.is_dir():
                    files = []
                else:
                    files = sorted(
                        (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".rdc"),
                        key=lambda path: (path.stat().st_mtime, path.name.lower()),
                        reverse=True,
                    )
            return self._ok({"files": [str(path) for path in files]}, logs=[f"found {len(files)} RDC files"])
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

    def shutdown(self, payload: dict | None = None) -> dict:
        try:
            stopped: list[int] = []
            for image_name, owned_pids in self._owned_mcp_pids.items():
                live_owned_pids = owned_pids.intersection(process_ids(image_name))
                for pid in sorted(live_owned_pids):
                    terminate_process_tree_by_pid(pid)
                    stopped.append(pid)
                owned_pids.difference_update(live_owned_pids)
            if stopped:
                release_session(OperationContext())
            return self._ok({"stopped_pids": stopped})
        except Exception as exc:
            return self._fail(exc)

    def _track_mcp_runtime_start(self, fn: Callable[[], Any]) -> Any:
        before = _mcp_pid_snapshot()
        result = fn()
        after = _mcp_pid_snapshot()
        for image_name in MCP_RUNTIME_IMAGES:
            self._owned_mcp_pids[image_name].update(after[image_name] - before[image_name])
        return result

    def _stop_mcp_from_gui(self, ctx: OperationContext) -> None:
        stop_mcp(ctx)
        for owned_pids in self._owned_mcp_pids.values():
            owned_pids.clear()

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


def _mcp_pid_snapshot() -> dict[str, set[int]]:
    return {image_name: set(process_ids(image_name)) for image_name in MCP_RUNTIME_IMAGES}


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
