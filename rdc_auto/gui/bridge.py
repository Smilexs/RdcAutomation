from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rdc_auto.config import load_config, save_config
from rdc_auto.errors import UserActionRequired
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
        return self._ok(build_status_snapshot(load_config()))

    def save_environment(self, payload: dict) -> dict:
        payload = payload or {}
        cfg = load_config()
        cfg.renderdoc.qrenderdoc_path = str(payload.get("renderdoc_path", "")).strip()
        cfg.emulator.root_dir = str(payload.get("mumu_root", "")).strip()
        cfg.emulator.vm_index = str(payload.get("vm_index", "")).strip()
        cfg.emulator.graphics_api = str(payload.get("graphics_api", "vulkan")).strip() or "vulkan"
        save_config(cfg)
        return self._ok(build_status_snapshot(cfg), logs=["environment config saved"])

    def save_mcp(self, payload: dict) -> dict:
        payload = payload or {}
        cfg = load_config()
        cfg.mcp.executable_path = str(payload.get("executable_path", payload.get("mcp_path", ""))).strip()
        save_config(cfg)
        return self._ok(build_status_snapshot(cfg), logs=["MCP config saved"])

    def save_ai(self, payload: dict) -> dict:
        payload = payload or {}
        cfg = load_config()
        cfg.ai.provider = str(payload.get("provider", "openai")).strip() or "openai"
        cfg.ai.model = str(payload.get("model", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
        cfg.ai.base_url = str(payload.get("base_url", "https://api.openai.com/v1")).strip() or "https://api.openai.com/v1"
        cfg.ai.api_key = ""
        save_config(cfg)
        return self._ok(build_status_snapshot(cfg), logs=["AI settings saved without persisting API key"])

    def test_ai(self, payload: dict | None = None) -> dict:
        return self._ok({"connected": True, "mode": "frontend-only"}, logs=["AI test uses local GUI mode"])

    def send_chat(self, payload: dict) -> dict:
        payload = payload or {}
        message = str(payload.get("message", "")).strip()
        return self._ok({"reply": _local_ai_reply(message)}, logs=["AI local reply generated"])

    def start_job(self, payload: dict) -> dict:
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
                        force=bool(params.get("force")),
                        confirm_vulkan=bool(params.get("confirm_vulkan")),
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

    def get_job(self, payload: dict) -> dict:
        payload = payload or {}
        return self._ok(self.jobs.get(str(payload.get("job_id", ""))))

    def choose_directory(self, payload: dict | None = None) -> dict:
        if self.window is None:
            return self._fail(UserActionRequired("The GUI window is not ready."))
        import webview

        payload = payload or {}
        result = self.window.create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=str(payload.get("initial_dir", "")),
        )
        return self._ok({"path": result[0] if result else ""})

    def choose_file(self, payload: dict | None = None) -> dict:
        if self.window is None:
            return self._fail(UserActionRequired("The GUI window is not ready."))
        import webview

        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("RenderDoc Capture (*.rdc)",),
        )
        return self._ok({"path": result[0] if result else ""})

    def open_path(self, payload: dict) -> dict:
        payload = payload or {}
        path = Path(str(payload.get("path", "")))
        if not path.exists():
            return self._fail(FileNotFoundError(str(path)))
        os.startfile(str(path))
        return self._ok({"opened": str(path)})

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
    return {"completed": True} if result is None else {"completed": True}


def _running(result: Any) -> dict[str, bool]:
    return {"running": True}


def _stopped(result: Any) -> dict[str, bool]:
    return {"running": False}


def _released(result: Any) -> dict[str, bool]:
    return {"released": True}


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
    if "attach" in lower or "连接" in message:
        return "建议先确认 MuMu12 已切换到 Vulkan，并关闭多余的 qrenderdoc.exe 实例。"
    if "mcp" in lower:
        return "建议先执行环境检测；如果提示扩展需要重启，请关闭 RenderDoc 后重试。"
    if "export" in lower or "导出" in message:
        return "建议确认 RDC 文件存在、MCP 正在运行，并检查输出目录是否可写。"
    return "建议按环境设置、Attach、捕获、导出的顺序排查，并查看底部日志中的具体错误。"
