from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from .errors import RdcAutoError


BRIDGE_EXTENSION_NAME = "rdc_auto_capture_bridge"
BRIDGE_IPC_DIR_NAME = "rdc_auto_capture_bridge"
BRIDGE_BOOTSTRAP_NAME = "bootstrap.py"


def capture_bridge_ipc_dir() -> Path:
    temp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or Path.home())
    return temp / BRIDGE_IPC_DIR_NAME


class CaptureBridgeClient:
    def __init__(
        self,
        ipc_dir: Path | None = None,
        poll_interval: float = 0.05,
        timeout: float = 30.0,
    ):
        self.ipc_dir = ipc_dir or capture_bridge_ipc_dir()
        self.poll_interval = poll_interval
        self.timeout = timeout

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        self.ipc_dir.mkdir(parents=True, exist_ok=True)
        request_id = str(uuid.uuid4())
        request_path = self.ipc_dir / "request.json"
        response_path = self.ipc_dir / "response.json"
        lock_path = self.ipc_dir / "lock"

        if response_path.exists():
            response_path.unlink()

        lock_path.write_text(request_id, encoding="utf-8")
        request_path.write_text(
            json.dumps({"id": request_id, "method": method, "params": params or {}}),
            encoding="utf-8",
        )
        lock_path.unlink(missing_ok=True)

        deadline = time.time() + (timeout if timeout is not None else self.timeout)
        while time.time() < deadline:
            if response_path.exists():
                raw = json.loads(response_path.read_text(encoding="utf-8"))
                response_path.unlink(missing_ok=True)
                if raw.get("id") != request_id:
                    continue
                if "error" in raw:
                    error = raw["error"]
                    raise RdcAutoError(str(error.get("message", error)))
                result = raw.get("result")
                return result if isinstance(result, dict) else {"value": result}
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Timed out waiting for rdc-auto capture bridge method {method}")

    def ping(self) -> bool:
        return self.call("ping", timeout=3.0).get("status") == "ok"


class CaptureBridgeInstaller:
    def __init__(self, extension_root: Path | None = None):
        self.extension_root = extension_root or _default_extension_root()

    def install(self) -> Path:
        target = self.extension_root / BRIDGE_EXTENSION_NAME
        target.mkdir(parents=True, exist_ok=True)
        _write_if_changed(target / "extension.json", EXTENSION_JSON)
        _write_if_changed(target / "__init__.py", EXTENSION_INIT)
        _write_if_changed(target / BRIDGE_BOOTSTRAP_NAME, _extension_bootstrap(target / "__init__.py"))
        self._ensure_always_load()
        return target

    def bootstrap_script(self) -> Path:
        return self.extension_root / BRIDGE_EXTENSION_NAME / BRIDGE_BOOTSTRAP_NAME

    def _ensure_always_load(self) -> None:
        config_path = self.extension_root.parent / "UI.config"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if config_path.is_file():
            raw = config_path.read_text(encoding="utf-8").strip()
            if raw:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    data = loaded

        entries = data.get("AlwaysLoad_Extensions", [])
        if isinstance(entries, str):
            entries = [entries]
        elif not isinstance(entries, list):
            entries = []
        if BRIDGE_EXTENSION_NAME not in entries:
            entries.append(BRIDGE_EXTENSION_NAME)
        data["AlwaysLoad_Extensions"] = entries
        _write_if_changed(config_path, json.dumps(data, indent=2) + "\n")


def _default_extension_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "qrenderdoc" / "extensions"
    return Path.home() / "AppData" / "Roaming" / "qrenderdoc" / "extensions"


def _write_if_changed(path: Path, content: str) -> None:
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def _extension_bootstrap(extension_init: Path) -> str:
    return EXTENSION_BOOTSTRAP_TEMPLATE.replace("__EXTENSION_INIT_PATH__", json.dumps(str(extension_init)))


EXTENSION_JSON = """{
  "extension_api": 1,
  "name": "rdc-auto Capture Bridge",
  "version": "1.0.0",
  "minimum_renderdoc": "1.44",
  "description": "Provides a small file IPC bridge for rdc-auto attach and capture.",
  "author": "rdc-auto"
}
"""


EXTENSION_INIT = r'''from __future__ import print_function

import datetime
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
import uuid

import renderdoc as rd

try:
    import qrenderdoc as qrd
    _HAS_QRENDERDOC = True
except Exception:
    _HAS_QRENDERDOC = False

IPC_DIR = os.path.join(tempfile.gettempdir(), "rdc_auto_capture_bridge")
REQUEST_FILE = os.path.join(IPC_DIR, "request.json")
RESPONSE_FILE = os.path.join(IPC_DIR, "response.json")
LOCK_FILE = os.path.join(IPC_DIR, "lock")

_server = None
_controller = None


def register(version, ctx):
    global _server, _controller
    if _server is not None and _server.is_running():
        print("[rdc-auto] Capture bridge already loaded (RenderDoc %s)" % version)
        return
    _controller = CaptureController(ctx)
    _server = FileIpcServer(_controller)
    _server.start()
    if _HAS_QRENDERDOC:
        try:
            ctx.Extensions().RegisterWindowMenu(
                qrd.WindowMenu.Tools, ["rdc-auto Capture Bridge", "Status"], _show_status
            )
        except Exception:
            pass
    print("[rdc-auto] Capture bridge loaded (RenderDoc %s)" % version)


def unregister():
    global _server
    if _server is not None:
        _server.stop()
        _server = None
    print("[rdc-auto] Capture bridge unloaded")


def _show_status(ctx, data):
    if _server is not None and _server.is_running():
        ctx.Extensions().MessageDialog("rdc-auto capture bridge is running", "rdc-auto")
    else:
        ctx.Extensions().ErrorDialog("rdc-auto capture bridge is not running", "rdc-auto")


class FileIpcServer(object):
    def __init__(self, controller):
        self.controller = controller
        self._running = False
        self._thread = None
        if not os.path.isdir(IPC_DIR):
            os.makedirs(IPC_DIR)

    def start(self):
        self._running = True
        self._cleanup()
        self._thread = threading.Thread(target=self._loop)
        self._thread.daemon = True
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None
        self._cleanup()

    def is_running(self):
        return self._running

    def _loop(self):
        while self._running:
            self._poll()
            time.sleep(0.05)

    def _cleanup(self):
        for path in (REQUEST_FILE, RESPONSE_FILE, LOCK_FILE):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    def _poll(self):
        if not os.path.exists(REQUEST_FILE) or os.path.exists(LOCK_FILE):
            return
        try:
            with open(REQUEST_FILE, "r") as f:
                request = json.load(f)
            os.remove(REQUEST_FILE)
            response = self._handle(request)
            with open(RESPONSE_FILE, "w") as f:
                json.dump(response, f)
        except Exception as e:
            print("[rdc-auto] Capture bridge IPC error: %s" % str(e))
            traceback.print_exc()

    def _handle(self, request):
        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {}) or {}
        try:
            if method == "ping":
                result = {"status": "ok"}
            elif method == "launch_application":
                result = self.controller.launch_application(**params)
            elif method == "connect_running_target":
                result = self.controller.connect_running_target(**params)
            elif method == "get_target_status":
                result = self.controller.get_target_status(params.get("session_id", ""))
            elif method == "trigger_capture":
                result = self.controller.trigger_capture(**params)
            elif method == "close_target":
                result = self.controller.close_target(params.get("session_id", ""))
            else:
                return {"id": request_id, "error": {"code": -32601, "message": "Unknown capture bridge method: %s" % method}}
            return {"id": request_id, "result": result}
        except Exception as e:
            traceback.print_exc()
            return {"id": request_id, "error": {"code": -32000, "message": str(e)}}


class CaptureController(object):
    def __init__(self, ctx):
        self.ctx = ctx
        self._target_sessions = {}

    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", timeout_seconds=60,
                           output_path="", target_process_name="", connect_target=True):
        exe_path, working_dir = self._validate_launch_paths(exe_path, working_dir)
        graphics_api = self._normalize_graphics_api(graphics_api)
        execute_and_inject, create_target_control = self._get_capture_entrypoints("launch_application")

        output_path = output_path or self._default_capture_path(exe_path)
        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir and not os.path.isdir(output_dir):
            os.makedirs(output_dir)
        capture_template = output_path[:-4] if output_path.lower().endswith(".rdc") else output_path

        try:
            exec_result = execute_and_inject(
                exe_path,
                working_dir,
                cmd_line or "",
                self._make_capture_env_mods(graphics_api),
                capture_template,
                self._make_capture_options(),
                False,
            )
        except Exception as e:
            raise ValueError("Failed to launch and inject: %s" % str(e))

        if not self._execute_result_ok(exec_result):
            raise ValueError("Failed to launch and inject: %s" % self._execute_result_message(exec_result))

        ident = int(getattr(exec_result, "ident", 0))
        if not self._as_bool(connect_target):
            return {
                "session_id": "",
                "pid": 0,
                "ident": ident,
                "status": "launched",
                "connected": False,
                "controllable": False,
            }

        target = self._connect_target(create_target_control, ident, timeout_seconds, target_process_name, graphics_api)
        if target is None:
            raise ValueError("Failed to connect to injected target process")
        return self._store_session(target, ident, exe_path, working_dir, cmd_line or "", graphics_api, capture_template)

    def connect_running_target(self, target_process_name="", graphics_api="auto", timeout_seconds=60):
        create_target_control = self._get_target_control_entrypoint("connect_running_target")
        expected_name = (target_process_name or "").strip()
        expected_api = self._normalize_graphics_api(graphics_api)
        deadline = time.time() + max(float(timeout_seconds), 5.0)
        last_targets = []

        while time.time() < deadline:
            last_targets = []
            for ident in self._candidate_target_idents(0, expected_name):
                target = self._connect_target_candidate(create_target_control, ident)
                if target is None:
                    continue
                info = self._describe_target(target, ident)
                last_targets.append(info)
                if expected_name and not self._target_name_matches(info.get("target_name", ""), expected_name):
                    self._shutdown_target(target)
                    continue
                if not self._target_api_matches_named_target(info.get("target_api", ""), expected_api):
                    self._shutdown_target(target)
                    continue
                return self._store_session(
                    target,
                    ident,
                    info.get("target_name", "") or expected_name,
                    "",
                    "",
                    expected_api,
                    self._default_capture_path(info.get("target_name", "") or expected_name),
                    extra=info,
                )
            time.sleep(1.0)

        raise ValueError(
            "No running RenderDoc target matched %s with API %s. Visible targets: %s"
            % (expected_name or "<any>", expected_api, self._format_targets(last_targets))
        )

    def get_target_status(self, session_id):
        session = self._target_sessions.get(session_id)
        if session is None:
            return {"session_id": session_id, "exists": False, "connected": False, "controllable": False, "status": "not_found"}
        target = session["target"]
        controllable = not self._target_disconnected(target)
        return {
            "session_id": session_id,
            "exists": True,
            "connected": controllable,
            "controllable": controllable,
            "status": "running" if controllable else "disconnected",
            "pid": session.get("pid", 0),
            "ident": session.get("ident", 0),
            "target_name": self._get_target_name(target) or session.get("target_name", ""),
            "target_api": self._get_target_api(target) or session.get("target_api", ""),
        }

    def trigger_capture(self, session_id, output_path="", timeout_seconds=60):
        session = self._target_sessions.get(session_id)
        if session is None:
            raise ValueError("Unknown target session: %s" % session_id)
        target = session["target"]
        if self._target_disconnected(target):
            raise ValueError("Target session is disconnected: %s" % session_id)

        output_path = output_path or self._default_capture_path(session.get("exe_path", "capture"))
        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir and not os.path.isdir(output_dir):
            os.makedirs(output_dir)

        capture_started_at = time.time()
        try:
            target.TriggerCapture(1)
        except Exception:
            try:
                target.QueueCapture(0, 1)
            except Exception as e:
                raise ValueError("Failed to trigger capture: %s" % str(e))

        found_capture = self._wait_for_capture_file(
            target,
            session.get("exe_path", ""),
            session.get("capture_template", output_path),
            output_path,
            timeout_seconds,
            capture_started_at,
        )
        if not found_capture or not os.path.isfile(found_capture):
            raise ValueError("Capture completed but no .rdc file was found")
        if os.path.abspath(found_capture) != os.path.abspath(output_path):
            self._copy_capture_file(found_capture, output_path, timeout_seconds)
        session["last_capture_path"] = output_path
        return {
            "success": True,
            "session_id": session_id,
            "capture_path": output_path,
            "rdc_path": output_path,
            "source_capture_path": found_capture,
            "status": "captured",
        }

    def close_target(self, session_id):
        session = self._target_sessions.pop(session_id, None)
        if session is None:
            return {"success": False, "session_id": session_id, "exists": False, "status": "not_found"}
        self._shutdown_target(session.get("target"))
        return {"success": True, "session_id": session_id, "exists": True, "status": "closed"}

    def _store_session(self, target, ident, exe_path, working_dir, cmd_line, graphics_api, capture_template, extra=None):
        info = extra or self._describe_target(target, ident)
        session_id = uuid.uuid4().hex
        self._target_sessions[session_id] = {
            "session_id": session_id,
            "target": target,
            "pid": info.get("pid", self._get_target_pid(target)),
            "ident": ident,
            "target_name": info.get("target_name", self._get_target_name(target)),
            "target_api": info.get("target_api", self._get_target_api(target)),
            "exe_path": exe_path,
            "working_dir": working_dir,
            "cmd_line": cmd_line,
            "graphics_api": graphics_api,
            "capture_template": capture_template,
            "started_at": time.time(),
            "last_capture_path": "",
        }
        result = dict(info)
        result.update({
            "session_id": session_id,
            "pid": self._target_sessions[session_id]["pid"],
            "ident": ident,
            "status": "running",
            "connected": not self._target_disconnected(target),
            "controllable": not self._target_disconnected(target),
        })
        return result

    def _validate_launch_paths(self, exe_path, working_dir=""):
        if not exe_path:
            raise ValueError("exe_path is required")
        if not os.path.isfile(exe_path):
            raise ValueError("Target executable not found: %s" % exe_path)
        working_dir = working_dir or os.path.dirname(os.path.abspath(exe_path))
        if not os.path.isdir(working_dir):
            raise ValueError("Working directory not found: %s" % working_dir)
        return exe_path, working_dir

    def _get_capture_entrypoints(self, tool_name):
        execute_and_inject = getattr(rd, "ExecuteAndInject", None) or getattr(rd, "RENDERDOC_ExecuteAndInject", None)
        create_target_control = getattr(rd, "CreateTargetControl", None) or getattr(rd, "RENDERDOC_CreateTargetControl", None)
        if execute_and_inject is None or create_target_control is None:
            raise ValueError("This RenderDoc Python build does not expose ExecuteAndInject/CreateTargetControl; %s is unavailable" % tool_name)
        return execute_and_inject, create_target_control

    def _get_target_control_entrypoint(self, tool_name):
        create_target_control = getattr(rd, "CreateTargetControl", None) or getattr(rd, "RENDERDOC_CreateTargetControl", None)
        if create_target_control is None:
            raise ValueError("This RenderDoc Python build does not expose CreateTargetControl; %s is unavailable" % tool_name)
        return create_target_control

    def _normalize_graphics_api(self, graphics_api):
        value = (graphics_api or "auto").strip().lower()
        aliases = {"": "auto", "default": "auto", "dx11": "d3d11", "dx12": "d3d12", "gl": "opengl", "opengles": "gles", "gles2": "gles", "gles3": "gles"}
        value = aliases.get(value, value)
        allowed = ("auto", "vulkan", "d3d11", "d3d12", "opengl", "gles")
        if value not in allowed:
            raise ValueError("Unsupported graphics_api '%s'. Expected one of: %s" % (graphics_api, ", ".join(allowed)))
        return value

    def _make_capture_options(self):
        try:
            opts = rd.CaptureOptions()
        except Exception:
            return None
        defaults = {
            "allowVSync": True,
            "allowFullscreen": True,
            "apiValidation": False,
            "captureCallstacks": False,
            "captureCallstacksOnlyActions": False,
            "delayForDebugger": 0,
            "verifyBufferAccess": False,
            "hookIntoChildren": True,
            "refAllResources": True,
            "captureAllCmdLists": False,
            "debugOutputMute": True,
            "softMemoryLimit": 0,
        }
        for name, value in defaults.items():
            try:
                setattr(opts, name, value)
            except Exception:
                pass
        return opts

    def _make_capture_env_mods(self, graphics_api="auto"):
        mods = []

        def append_env(name, value):
            try:
                mod = rd.EnvironmentModification()
                mod.mod = rd.EnvMod.Set
                mod.sep = rd.EnvSep.NoSep
                mod.name = name
                mod.value = value
                mods.append(mod)
            except Exception:
                pass

        if graphics_api in ("auto", "vulkan"):
            append_env("ENABLE_VULKAN_RENDERDOC_CAPTURE", "1")
            runtime_dir = self._renderdoc_runtime_dir()
            if runtime_dir:
                append_env("VK_IMPLICIT_LAYER_PATH", runtime_dir)
        return mods

    def _renderdoc_runtime_dir(self):
        candidates = []
        module_path = getattr(rd, "__file__", "")
        if module_path:
            candidates.append(os.path.dirname(os.path.abspath(module_path)))
        try:
            candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
        except Exception:
            pass
        for candidate in candidates:
            if candidate and os.path.isdir(candidate):
                return candidate
        return ""

    def _execute_result_ok(self, exec_result):
        try:
            result = getattr(exec_result, "result", None)
            code = getattr(result, "code", None)
            if code is not None:
                return code == rd.ResultCode.Succeeded
        except Exception:
            pass
        try:
            status = getattr(exec_result, "status", None)
            if status is not None:
                return "Succeeded" in str(status)
        except Exception:
            pass
        return int(getattr(exec_result, "ident", 0)) > 0

    def _execute_result_message(self, exec_result):
        try:
            result = getattr(exec_result, "result", None)
            return str(result.Message())
        except Exception:
            return str(exec_result)

    def _connect_target(self, create_target_control, ident, timeout_seconds, target_process_name="", graphics_api="auto"):
        expected_name = (target_process_name or "").strip()
        expected_api = self._normalize_graphics_api(graphics_api)
        deadline = time.time() + max(float(timeout_seconds), 5.0)
        fallback_target = None
        while time.time() < deadline:
            for candidate in self._candidate_target_idents(ident, expected_name):
                target = self._connect_target_candidate(create_target_control, candidate)
                if target is None:
                    continue
                target_name = self._get_target_name(target)
                target_api = self._get_target_api(target)
                if expected_name and not self._target_name_matches(target_name, expected_name):
                    self._shutdown_target(target)
                    continue
                if not expected_name or self._target_api_matches(target_api, expected_api):
                    if fallback_target is not None and fallback_target is not target:
                        self._shutdown_target(fallback_target)
                    return target
                if fallback_target is None:
                    fallback_target = target
                else:
                    self._shutdown_target(target)
            if fallback_target is not None:
                if self._target_disconnected(fallback_target):
                    fallback_target = None
                elif self._target_api_matches(self._get_target_api(fallback_target), expected_api):
                    return fallback_target
                else:
                    self._receive_message(fallback_target)
            time.sleep(1.0)
        return fallback_target

    def _candidate_target_idents(self, ident, expected_name=""):
        fallback = []
        for candidate in (ident + 1, ident + 2, ident, ident - 1):
            if candidate > 0 and candidate not in fallback:
                fallback.append(candidate)
        for offset in range(3, 11):
            for candidate in (ident + offset, ident - offset):
                if candidate > 0 and candidate not in fallback:
                    fallback.append(candidate)
        enumerated = self._enumerate_target_idents()
        candidates = enumerated + fallback if expected_name else fallback + enumerated
        result = []
        for candidate in candidates:
            if candidate > 0 and candidate not in result:
                result.append(candidate)
        return result

    def _enumerate_target_idents(self):
        enumerate_targets = getattr(rd, "EnumerateRemoteTargets", None) or getattr(rd, "RENDERDOC_EnumerateRemoteTargets", None)
        if enumerate_targets is None:
            return []
        idents = []
        next_ident = 0
        for _ in range(128):
            try:
                ident = int(enumerate_targets("", next_ident))
            except Exception:
                break
            if ident <= 0 or ident in idents:
                break
            idents.append(ident)
            next_ident = ident
        return idents

    def _connect_target_candidate(self, create_target_control, ident):
        try:
            return create_target_control("", int(ident), "rdc-auto-capture-bridge", True)
        except Exception:
            return None

    def _describe_target(self, target, ident):
        return {
            "ident": int(ident),
            "pid": self._get_target_pid(target),
            "target_name": self._get_target_name(target),
            "target_api": self._get_target_api(target),
            "connected": not self._target_disconnected(target),
        }

    def _format_targets(self, targets):
        if not targets:
            return "none"
        parts = []
        for target in targets:
            parts.append("ident=%s pid=%s name=%s api=%s connected=%s" % (
                target.get("ident", ""),
                target.get("pid", ""),
                target.get("target_name", ""),
                target.get("target_api", ""),
                target.get("connected", ""),
            ))
        return "; ".join(parts)

    def _target_name_matches(self, target_name, expected_name):
        target = (target_name or "").lower()
        expected = (expected_name or "").lower()
        names = []

        def append_name(name):
            if name and name not in names:
                names.append(name)
            if "mumuvmheadless" in name:
                alias = name.replace("mumuvmheadless", "mumuvmmheadless")
                if alias not in names:
                    names.append(alias)
            if "mumuvmmheadless" in name:
                alias = name.replace("mumuvmmheadless", "mumuvmheadless")
                if alias not in names:
                    names.append(alias)

        append_name(expected)
        if expected.endswith(".exe"):
            append_name(expected[:-4])
        else:
            append_name(expected + ".exe")
        return any(name and name in target for name in names)

    def _target_api_matches_named_target(self, target_api, expected_api):
        if self._target_api_matches(target_api, expected_api):
            return True
        return not (target_api or "").strip()

    def _target_api_matches(self, target_api, expected_api):
        api = (target_api or "").lower()
        expected = (expected_api or "auto").lower()
        if not api:
            return False
        if expected in ("", "auto"):
            return True
        return expected in api

    def _get_target_pid(self, target):
        try:
            return int(target.GetPID())
        except Exception:
            return 0

    def _get_target_name(self, target):
        try:
            return str(target.GetTarget())
        except Exception:
            return ""

    def _get_target_api(self, target):
        try:
            return str(target.GetAPI())
        except Exception:
            return ""

    def _default_capture_path(self, exe_path):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        exe_name = os.path.splitext(os.path.basename(exe_path or "capture"))[0]
        directory = os.path.join(tempfile.gettempdir(), "rdc_auto_captures")
        if not os.path.isdir(directory):
            os.makedirs(directory)
        return os.path.join(directory, "%s_%s.rdc" % (exe_name, stamp))

    def _wait_for_capture_file(self, target, exe_path, capture_template, output_path, timeout_seconds, min_mtime=0):
        deadline = time.time() + max(float(timeout_seconds), 5.0)
        while time.time() < deadline:
            if self._target_disconnected(target):
                break
            msg = self._receive_message(target)
            msg_type = self._message_type_name(msg)
            if "NewCapture" in msg_type:
                new_capture = getattr(msg, "newCapture", None)
                capture_path = ""
                capture_id = None
                try:
                    capture_path = str(new_capture.path)
                except Exception:
                    pass
                try:
                    capture_id = new_capture.ID
                except Exception:
                    try:
                        capture_id = new_capture.id
                    except Exception:
                        pass
                if capture_id is not None:
                    copied = self._copy_capture(target, capture_id, output_path)
                    if copied:
                        return copied
                if capture_path and os.path.isfile(capture_path):
                    return capture_path
            if "Disconnected" in msg_type:
                break
            scanned = self._find_newest_capture(exe_path, capture_template, min_mtime)
            if scanned:
                return scanned
            time.sleep(0.1)
        return self._find_newest_capture(exe_path, capture_template, min_mtime)

    def _copy_capture(self, target, capture_id, output_path):
        try:
            target.CopyCapture(capture_id, output_path)
        except Exception:
            return ""
        deadline = time.time() + 30.0
        while time.time() < deadline:
            if os.path.isfile(output_path):
                return output_path
            self._receive_message(target)
            time.sleep(0.1)
        return output_path if os.path.isfile(output_path) else ""

    def _copy_capture_file(self, source_path, output_path, timeout_seconds=30):
        deadline = time.time() + max(float(timeout_seconds), 5.0)
        last_error = None
        while time.time() < deadline:
            try:
                shutil.copyfile(source_path, output_path)
                if os.path.isfile(output_path):
                    return output_path
            except Exception as e:
                last_error = e
            time.sleep(0.25)
        raise ValueError("Failed to copy captured .rdc file from %s to %s: %s" % (source_path, output_path, last_error))

    def _find_newest_capture(self, exe_path, capture_template, min_mtime=0):
        exe_name = os.path.splitext(os.path.basename(exe_path or ""))[0].lower()
        search_dirs = [
            os.path.dirname(os.path.abspath(capture_template)),
            os.path.join(tempfile.gettempdir(), "RenderDoc"),
            os.path.join(tempfile.gettempdir(), "rdc_auto_captures"),
        ]
        newest = ""
        newest_time = 0
        for directory in search_dirs:
            if not directory or not os.path.isdir(directory):
                continue
            try:
                for filename in os.listdir(directory):
                    if not filename.lower().endswith(".rdc"):
                        continue
                    lower_name = filename.lower()
                    if exe_name and exe_name not in lower_name:
                        continue
                    path = os.path.join(directory, filename)
                    mtime = os.path.getmtime(path)
                    if min_mtime and mtime < float(min_mtime) - 1.0:
                        continue
                    if mtime > newest_time:
                        newest = path
                        newest_time = mtime
            except Exception:
                pass
        return newest

    def _receive_message(self, target):
        try:
            return target.ReceiveMessage(None)
        except TypeError:
            try:
                return target.ReceiveMessage()
            except Exception:
                return None
        except Exception:
            return None

    def _message_type_name(self, msg):
        if msg is None:
            return ""
        try:
            return str(msg.type)
        except Exception:
            return str(type(msg))

    def _target_disconnected(self, target):
        try:
            return not bool(target.Connected())
        except Exception:
            return False

    def _shutdown_target(self, target):
        try:
            if target is not None:
                target.Shutdown()
        except Exception:
            pass

    def _as_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off")
        return bool(value)
'''


EXTENSION_BOOTSTRAP_TEMPLATE = r'''from __future__ import print_function

import importlib.util
import json
import os
import sys
import tempfile
import time
import traceback
import uuid

MODULE_NAME = "rdc_auto_capture_bridge"
EXTENSION_INIT = __EXTENSION_INIT_PATH__
IPC_DIR = os.path.join(tempfile.gettempdir(), "rdc_auto_capture_bridge")
REQUEST_FILE = os.path.join(IPC_DIR, "request.json")
RESPONSE_FILE = os.path.join(IPC_DIR, "response.json")
LOCK_FILE = os.path.join(IPC_DIR, "lock")


def _bridge_already_running():
    try:
        if not os.path.isdir(IPC_DIR):
            return False
        request_id = uuid.uuid4().hex
        if os.path.exists(RESPONSE_FILE):
            os.remove(RESPONSE_FILE)
        with open(LOCK_FILE, "w") as f:
            f.write(request_id)
        with open(REQUEST_FILE, "w") as f:
            json.dump({"id": request_id, "method": "ping", "params": {}}, f)
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass

        deadline = time.time() + 1.0
        while time.time() < deadline:
            if os.path.exists(RESPONSE_FILE):
                with open(RESPONSE_FILE, "r") as f:
                    response = json.load(f)
                try:
                    os.remove(RESPONSE_FILE)
                except Exception:
                    pass
                return response.get("id") == request_id and response.get("result", {}).get("status") == "ok"
            time.sleep(0.05)
    except Exception:
        return False
    return False


def _load_bridge_module():
    module = sys.modules.get(MODULE_NAME)
    if module is not None and hasattr(module, "register"):
        return module
    spec = importlib.util.spec_from_file_location(MODULE_NAME, EXTENSION_INIT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _renderdoc_version():
    try:
        return renderdoc.GetVersionString()
    except Exception:
        return "unknown"


try:
    if _bridge_already_running():
        print("[rdc-auto] Capture bridge already running")
    else:
        _load_bridge_module().register(_renderdoc_version(), pyrenderdoc)
except Exception:
    print("[rdc-auto] Failed to bootstrap capture bridge")
    traceback.print_exc()
    raise
'''
