from __future__ import annotations

from pathlib import Path

from rdc_auto.mcp_patch import patch_renderdoc_mcp_extension


def _write_minimal_extension(extension: Path) -> None:
    services = extension / "services"
    services.mkdir(parents=True)
    (extension / "__init__.py").write_text(
        '''def register(version, ctx):
    _server = socket_server.MCPBridgeServer(
        host="127.0.0.1", port=19876, handler=handler
    )
''',
        encoding="utf-8",
    )
    (extension / "socket_server.py").write_text(
        '''import json
import os
import threading
import time
import traceback


class MCPBridgeServer(object):
    def __init__(self, host, port, handler):
        self.handler = handler
        self._thread = None
        self._running = False

    def _poll_request(self):
        try:
            response = self.handler.handle(request)
        except Exception as e:
            traceback.print_exc()
            response = {
                "id": request.get("id"),
                "error": {"code": -32603, "message": str(e)}
            }
''',
        encoding="utf-8",
    )
    (extension / "request_handler.py").write_text(
        '''    def __init__(self, facade):
        self.facade = facade
        self._methods = {
            "launch_application": self._handle_launch_application,
            "get_target_status": self._handle_get_target_status,
        }

    def _handle_launch_application(self, params):
        """Handle launch_application request"""
        exe_path = params.get("exe_path", params.get("exePath"))
        if not exe_path:
            raise ValueError("exe_path is required")
        return self.facade.launch_application(
            exe_path,
            params.get("working_dir", params.get("workingDir", "")),
            params.get("cmd_line", params.get("cmdLine", "")),
            params.get("graphics_api", params.get("graphicsApi", "auto")),
        )

    def _handle_get_target_status(self, params):
        return self.facade.get_target_status(params["session_id"])
''',
        encoding="utf-8",
    )
    (extension / "renderdoc_facade.py").write_text(
        '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto"):
        """Launch a target app through RenderDoc and keep TargetControl open"""
        return self._capture.launch_application(
            exe_path, working_dir, cmd_line, graphics_api)

    def get_target_status(self, session_id):
        return self._capture.get_target_status(session_id)
''',
        encoding="utf-8",
    )
    (services / "capture_manager.py").write_text(
        '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", timeout_seconds=60,
                           output_path=""):
        target = self._connect_target(create_target_control, ident, timeout_seconds)
        self._target_sessions[session_id] = {
            "session_id": session_id,
            "target": target,
            "pid": pid,
            "ident": ident,
        }
        return {
            "session_id": session_id,
            "pid": pid,
            "ident": ident,
        }

    def get_target_status(self, session_id):
        return {
            "session_id": session_id,
            "pid": session.get("pid", 0),
            "ident": session.get("ident", 0),
        }

    def _connect_target(self, create_target_control, ident, timeout_seconds):
        candidates = []
        for candidate in (ident + 1, ident + 2, ident, ident - 1):
            if candidate > 0 and candidate not in candidates:
                candidates.append(candidate)

        deadline = time.time() + max(float(timeout_seconds), 5.0)
        while time.time() < deadline:
            for candidate in list(candidates):
                try:
                    target = create_target_control(
                        "", int(candidate), "renderdoc-mcp", True)
                    if target:
                        return target
                except Exception:
                    pass
            for offset in range(3, 11):
                for candidate in (ident + offset, ident - offset):
                    if candidate > 0 and candidate not in candidates:
                        candidates.append(candidate)
            time.sleep(1.0)
        return None

    def _wait_for_capture_file(self, target, exe_path, capture_template,
                               output_path, timeout_seconds, min_mtime=0):
        return ""
''',
        encoding="utf-8",
    )


def test_patch_renderdoc_mcp_extension_adds_target_process_selection(tmp_path):
    exe = tmp_path / "renderdoc-mcp.exe"
    exe.write_bytes(b"exe")
    extension = tmp_path / "renderdoc_extension"
    _write_minimal_extension(extension)

    assert patch_renderdoc_mcp_extension(exe) is True

    patched_request = (extension / "request_handler.py").read_text(encoding="utf-8")
    assert "target_process_name" in patched_request
    assert "targetProcessName" in patched_request
    assert "connect_target" in patched_request
    assert "connect_running_target" in patched_request
    assert "list_running_targets" in patched_request

    patched_facade = (extension / "renderdoc_facade.py").read_text(encoding="utf-8")
    assert 'target_process_name=""' in patched_facade
    assert "target_process_name=target_process_name" in patched_facade
    assert "connect_running_target" in patched_facade
    assert "list_running_targets" in patched_facade

    patched_capture = (extension / "services" / "capture_manager.py").read_text(encoding="utf-8")
    assert 'target_process_name=""' in patched_capture
    assert "connect_target=True" in patched_capture
    assert "EnumerateRemoteTargets" in patched_capture
    assert "GetTarget" in patched_capture
    assert "GetAPI" in patched_capture
    assert "def connect_running_target" in patched_capture
    assert "def list_running_targets" in patched_capture

    patched_socket = (extension / "socket_server.py").read_text(encoding="utf-8")
    assert "QtMainThreadDispatcher" in patched_socket
    assert "self.dispatcher.call(self.handler.handle, request)" in patched_socket

    patched_init = (extension / "__init__.py").read_text(encoding="utf-8")
    assert "QtMainThreadDispatcher" in patched_init
    assert "dispatcher=dispatcher" in patched_init


def test_patch_renderdoc_mcp_extension_patches_loaded_qrenderdoc_extension(tmp_path, monkeypatch):
    exe = tmp_path / "RenderDocMCP" / "renderdoc-mcp.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"exe")
    _write_minimal_extension(exe.parent / "renderdoc_extension")

    appdata = tmp_path / "Roaming"
    loaded_extension = appdata / "qrenderdoc" / "extensions" / "renderdoc_mcp_bridge"
    _write_minimal_extension(loaded_extension)
    monkeypatch.setenv("APPDATA", str(appdata))

    assert patch_renderdoc_mcp_extension(exe) is True

    assert "QtMainThreadDispatcher" in (loaded_extension / "socket_server.py").read_text(encoding="utf-8")
    assert "dispatcher=dispatcher" in (loaded_extension / "__init__.py").read_text(encoding="utf-8")


def test_patch_renderdoc_mcp_extension_is_idempotent(tmp_path):
    exe = tmp_path / "renderdoc-mcp.exe"
    exe.write_bytes(b"exe")
    extension = tmp_path / "renderdoc_extension"
    services = extension / "services"
    services.mkdir(parents=True)

    for path in [
        extension / "request_handler.py",
        extension / "renderdoc_facade.py",
        services / "capture_manager.py",
    ]:
        path.write_text("# rdc-auto-capture-connect-patch-v2\n", encoding="utf-8")

    assert patch_renderdoc_mcp_extension(exe) is False
