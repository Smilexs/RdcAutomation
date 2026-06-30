from __future__ import annotations

import py_compile
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


def test_patch_renderdoc_mcp_extension_repairs_corrupted_dispatcher_block(tmp_path):
    exe = tmp_path / "renderdoc-mcp.exe"
    exe.write_bytes(b"exe")
    extension = tmp_path / "renderdoc_extension"
    extension.mkdir()
    socket_server = extension / "socket_server.py"
    socket_server.write_text(
        '''# rdc-auto-renderdocmcp-ui-thread-patch-v1
class MCPBridgeServer(object):
    def __init__(self, host, port, handler, dispatcher=None):
        self.handler = handler
        self.dispatcher = dispatcher
        self.dispatcher = dispatcher

    def _poll_request(self):
        try:
            if self.dispatcher is not None:
                response = self.dispatcher.call(self.handler.handle, request)
            else:
                if self.dispatcher is not None:
                response = self.dispatcher.call(self.handler.handle, request)
            else:
                response = self.handler.handle(request)
        except Exception:
            response = None
''',
        encoding="utf-8",
    )

    assert patch_renderdoc_mcp_extension(exe) is True

    repaired = socket_server.read_text(encoding="utf-8")
    assert "self.dispatcher = dispatcher\n        self.dispatcher = dispatcher" not in repaired
    assert "if self.dispatcher is not None:\n                response = self.dispatcher.call" in repaired
    assert "else:\n                response = self.handler.handle(request)" in repaired
    py_compile.compile(str(socket_server), doraise=True)


def test_patch_renderdoc_mcp_extension_wraps_replay_callback_exceptions(tmp_path):
    exe = tmp_path / "renderdoc-mcp.exe"
    exe.write_bytes(b"exe")
    extension = tmp_path / "renderdoc_extension"
    extension.mkdir()
    facade = extension / "renderdoc_facade.py"
    facade.write_text(
        '''class RenderDocFacade:
    def __init__(self, ctx):
        self.ctx = ctx

    def _invoke(self, callback):
        """Invoke callback on replay thread via BlockInvoke"""
        self.ctx.Replay().BlockInvoke(callback)
''',
        encoding="utf-8",
    )

    assert patch_renderdoc_mcp_extension(exe) is True

    patched = facade.read_text(encoding="utf-8")
    assert "rdc-auto-renderdocmcp-replay-invoke-patch-v1" in patched
    assert "def guarded_callback(controller):" in patched
    assert "traceback.format_exc()" in patched
    assert "BlockInvoke(guarded_callback)" in patched
    py_compile.compile(str(facade), doraise=True)


def test_patch_renderdoc_mcp_extension_wraps_replay_callback_when_connect_patch_already_exists(tmp_path):
    exe = tmp_path / "renderdoc-mcp.exe"
    exe.write_bytes(b"exe")
    extension = tmp_path / "renderdoc_extension"
    extension.mkdir()
    facade = extension / "renderdoc_facade.py"
    facade.write_text(
        '''# rdc-auto-capture-connect-patch-v2
class RenderDocFacade:
    def __init__(self, ctx):
        self.ctx = ctx

    def _invoke(self, callback):
        """Invoke callback on replay thread via BlockInvoke"""
        self.ctx.Replay().BlockInvoke(callback)
''',
        encoding="utf-8",
    )

    assert patch_renderdoc_mcp_extension(exe) is True

    patched = facade.read_text(encoding="utf-8")
    assert "rdc-auto-capture-connect-patch-v2" in patched
    assert "rdc-auto-renderdocmcp-replay-invoke-patch-v1" in patched
    assert "BlockInvoke(guarded_callback)" in patched


def test_patch_renderdoc_mcp_extension_skips_short_optional_mesh_attributes(tmp_path, monkeypatch):
    exe = tmp_path / "renderdoc-mcp.exe"
    exe.write_bytes(b"exe")
    extension = tmp_path / "renderdoc_extension"
    services = extension / "services"
    services.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    mesh_service = services / "mesh_service.py"
    mesh_service.write_text(
        '''def _normalize3(v):
    m = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
    if m < 1e-12:
        return [0.0, 0.0, 0.0]
    return [v[0] / m, v[1] / m, v[2] / m]


class MeshService:
    def export_mesh_to_file(self):
        out_nrm = []
        out_tan = []
        out_uv0 = []
        out_uv1 = []
        uv0 = uv1 = nrm = tan = [[1.0, 2.0]]
        bake_world = False
        def callback():
            for i in range(1):
                if nrm is not None:
                    nv = nrm[i]
                    if bake_world:
                        out_nrm.append(_bake_normal_worldtoobject(w2o, nv))
                    else:
                        out_nrm.append(_normalize3([nv[0], nv[1], nv[2]]))

                if tan is not None:
                    tv = tan[i]
                    tw = tv[3] if len(tv) > 3 else 1.0
                    if bake_world:
                        d = _bake_dir_objecttoworld(o2w, tv)
                    else:
                        d = _normalize3([tv[0], tv[1], tv[2]])
                    out_tan.append([d[0], d[1], d[2], tw])

            if uv0 is not None:
                raw_json["uv0"] = [[u[0], u[1]] for u in uv0]
            if uv1 is not None:
                raw_json["uv1"] = [[u[0], u[1]] for u in uv1]
''',
        encoding="utf-8",
    )

    assert patch_renderdoc_mcp_extension(exe) is True

    patched = mesh_service.read_text(encoding="utf-8")
    assert "rdc-auto-renderdocmcp-mesh-optional-attrs-patch-v1" in patched
    assert "_rdc_auto_has_components(nv, 3)" in patched
    assert "_rdc_auto_has_components(tv, 3)" in patched
    assert "_rdc_auto_vec2_list(uv0)" in patched
    assert "_rdc_auto_vec2_list(uv1)" in patched
    py_compile.compile(str(mesh_service), doraise=True)


def test_patch_renderdoc_mcp_extension_infers_mesh_slots_when_request_omits_slot_params(tmp_path, monkeypatch):
    exe = tmp_path / "renderdoc-mcp.exe"
    exe.write_bytes(b"exe")
    extension = tmp_path / "renderdoc_extension"
    services = extension / "services"
    services.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

    (extension / "request_handler.py").write_text(
        '''    def _handle_export_mesh_to_file(self, params):
        """Handle export_mesh_to_file request"""
        event_id = params.get("event_id")
        if event_id is None:
            raise ValueError("event_id is required")
        output_path = params.get("output_path")
        if not output_path:
            raise ValueError("output_path is required")
        return self.facade.export_mesh_to_file(
            int(event_id),
            output_path,
            bool(params.get("bake_world", True)),
            int(params.get("pos_slot", 0)),
            int(params.get("normal_slot", 1)),
            int(params.get("tangent_slot", 2)),
            int(params.get("uv0_slot", 3)),
            int(params.get("uv1_slot", 4)),
            int(params.get("extra_slot", 5)),
            int(params.get("o2w_offset", 32)),
            int(params.get("w2o_offset", 96)),
        )
''',
        encoding="utf-8",
    )
    mesh_service = services / "mesh_service.py"
    mesh_service.write_text(
        '''def _normalize3(v):
    m = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
    if m < 1e-12:
        return [0.0, 0.0, 0.0]
    return [v[0] / m, v[1] / m, v[2] / m]


class MeshService:
    def export_mesh_to_file(self, event_id, output_path, bake_world=True,
                            pos_slot=0, normal_slot=1, tangent_slot=2,
                            uv0_slot=3, uv1_slot=4, extra_slot=5,
                            o2w_offset=32, w2o_offset=96):
        def callback(controller):
            attrs_by_slot = {a["vertex_buffer_slot"]: a for a in data["attributes"]}

            def vals(slot):
                a = attrs_by_slot.get(slot)
                return a["values"] if a else None

            pos = vals(pos_slot)
            nrm = vals(normal_slot)
            tan = vals(tangent_slot)
            uv0 = vals(uv0_slot)
            uv1 = vals(uv1_slot)
            extra = vals(extra_slot)
''',
        encoding="utf-8",
    )

    assert patch_renderdoc_mcp_extension(exe) is True

    patched_request = (extension / "request_handler.py").read_text(encoding="utf-8")
    assert 'params.get("pos_slot", params.get("posSlot", -1))' in patched_request
    assert 'params.get("tangent_slot", params.get("tangentSlot", -1))' in patched_request

    patched_mesh = (services / "mesh_service.py").read_text(encoding="utf-8")
    assert "rdc-auto-renderdocmcp-mesh-slot-inference-patch-v1" in patched_mesh
    assert "slot_map = _rdc_auto_infer_slot_map(" in patched_mesh
    assert 'pos_slot = slot_map["position"]' in patched_mesh
    assert 'uv0_slot = slot_map["uv0"]' in patched_mesh
    py_compile.compile(str(mesh_service), doraise=True)
