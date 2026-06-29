from __future__ import annotations

import os
import re
from pathlib import Path


CONNECT_PATCH_MARKER = "# rdc-auto-capture-connect-patch-v2"
UI_THREAD_PATCH_MARKER = "# rdc-auto-renderdocmcp-ui-thread-patch-v1"
PATCH_MARKER = CONNECT_PATCH_MARKER


def patch_renderdoc_mcp_extension(executable_path: str | Path) -> bool:
    changed = False
    for extension_dir in _candidate_extension_dirs(executable_path):
        changed |= _patch_extension_dir(extension_dir)
    return changed


def _candidate_extension_dirs(executable_path: str | Path) -> list[Path]:
    candidates = [
        Path(executable_path).parent / "renderdoc_extension",
        _loaded_qrenderdoc_extension_dir(),
    ]
    result = []
    seen = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except OSError:
            key = str(candidate).lower()
        if key in seen or not candidate.is_dir():
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _loaded_qrenderdoc_extension_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "qrenderdoc" / "extensions" / "renderdoc_mcp_bridge"
    return Path.home() / "AppData" / "Roaming" / "qrenderdoc" / "extensions" / "renderdoc_mcp_bridge"


def _patch_extension_dir(extension_dir: Path) -> bool:
    changed = False
    changed |= _patch_extension_init(extension_dir / "__init__.py")
    changed |= _patch_socket_server(extension_dir / "socket_server.py")
    changed |= _patch_request_handler(extension_dir / "request_handler.py")
    changed |= _patch_facade(extension_dir / "renderdoc_facade.py")
    changed |= _patch_capture_manager(extension_dir / "services" / "capture_manager.py")
    return changed


def _patch_extension_init(path: Path) -> bool:
    if not path.is_file():
        return False

    text = path.read_text(encoding="utf-8")
    if UI_THREAD_PATCH_MARKER in text:
        return False

    original = text
    old = '''    _server = socket_server.MCPBridgeServer(
        host="127.0.0.1", port=19876, handler=handler
    )
'''
    new = '''    dispatcher = socket_server.QtMainThreadDispatcher()
    _server = socket_server.MCPBridgeServer(
        host="127.0.0.1", port=19876, handler=handler, dispatcher=dispatcher
    )
'''
    if old in text:
        text = text.replace(old, new, 1)

    if text == original:
        return False

    path.write_text(f"{UI_THREAD_PATCH_MARKER}\n{text}", encoding="utf-8")
    return True


def _patch_socket_server(path: Path) -> bool:
    if not path.is_file():
        return False

    text = path.read_text(encoding="utf-8")
    original = text
    text = _repair_socket_server_text(text)
    if UI_THREAD_PATCH_MARKER in text:
        if text != original:
            path.write_text(text, encoding="utf-8")
            return True
        return False

    class_marker = "class MCPBridgeServer(object):"
    if "class QtMainThreadDispatcher" not in text and class_marker in text:
        text = text.replace(class_marker, _QT_DISPATCHER_CODE + "\n\n" + class_marker, 1)

    text = text.replace(
        "    def __init__(self, host, port, handler):\n",
        "    def __init__(self, host, port, handler, dispatcher=None):\n",
        1,
    )
    text = text.replace(
        "        self.handler = handler\n",
        "        self.handler = handler\n        self.dispatcher = dispatcher\n",
        1,
    )
    dispatch_block_16 = '''                if self.dispatcher is not None:
                    response = self.dispatcher.call(self.handler.handle, request)
                else:
                    response = self.handler.handle(request)
'''
    dispatch_block_12 = '''            if self.dispatcher is not None:
                response = self.dispatcher.call(self.handler.handle, request)
            else:
                response = self.handler.handle(request)
'''
    if "                response = self.handler.handle(request)\n" in text:
        text = text.replace("                response = self.handler.handle(request)\n", dispatch_block_16, 1)
    elif "            response = self.handler.handle(request)\n" in text:
        text = text.replace("            response = self.handler.handle(request)\n", dispatch_block_12, 1)

    if text == original:
        return False

    path.write_text(f"{UI_THREAD_PATCH_MARKER}\n{text}", encoding="utf-8")
    return True


def _repair_socket_server_text(text: str) -> str:
    text = text.replace(
        "        self.dispatcher = dispatcher\n        self.dispatcher = dispatcher\n",
        "        self.dispatcher = dispatcher\n",
    )
    return re.sub(
        r"(?m)^([ \t]+)else:\n"
        r"\1    if self\.dispatcher is not None:\n"
        r"\1    response = self\.dispatcher\.call\(self\.handler\.handle, request\)\n"
        r"\1else:\n"
        r"\1    response = self\.handler\.handle\(request\)\n",
        lambda match: f"{match.group(1)}else:\n{match.group(1)}    response = self.handler.handle(request)\n",
        text,
    )


def _patch_request_handler(path: Path) -> bool:
    if not path.is_file():
        return False

    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        return False

    original = text
    for old in [_REQUEST_LAUNCH_ORIGINAL, _REQUEST_LAUNCH_V1]:
        if old in text:
            text = text.replace(old, _REQUEST_LAUNCH_V2, 1)
            break

    launch_entry = '            "launch_application": self._handle_launch_application,\n'
    connect_entries = (
        '            "connect_running_target": self._handle_connect_running_target,\n'
        '            "list_running_targets": self._handle_list_running_targets,\n'
    )
    if '"connect_running_target"' not in text and launch_entry in text:
        text = text.replace(launch_entry, launch_entry + connect_entries, 1)

    if "def _handle_connect_running_target" not in text:
        marker = "    def _handle_get_target_status(self, params):\n"
        if marker in text:
            text = text.replace(marker, _REQUEST_HANDLER_CONNECT_METHODS + marker, 1)

    if text == original:
        return False

    path.write_text(f"{PATCH_MARKER}\n{text}", encoding="utf-8")
    return True


def _patch_facade(path: Path) -> bool:
    if not path.is_file():
        return False

    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        return False

    original = text
    replacements = [
        (
            '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto"):
''',
            '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", target_process_name="", connect_target=True):
''',
        ),
        (
            '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", target_process_name=""):
''',
            '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", target_process_name="", connect_target=True):
''',
        ),
        (
            '''        return self._capture.launch_application(
            exe_path, working_dir, cmd_line, graphics_api)
''',
            '''        return self._capture.launch_application(
            exe_path, working_dir, cmd_line, graphics_api,
            target_process_name=target_process_name,
            connect_target=connect_target)
''',
        ),
        (
            '''        return self._capture.launch_application(
            exe_path, working_dir, cmd_line, graphics_api,
            target_process_name=target_process_name)
''',
            '''        return self._capture.launch_application(
            exe_path, working_dir, cmd_line, graphics_api,
            target_process_name=target_process_name,
            connect_target=connect_target)
''',
        ),
    ]
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)

    if "def connect_running_target" not in text:
        marker = "    def get_target_status(self, session_id):\n"
        if marker in text:
            text = text.replace(marker, _FACADE_CONNECT_METHODS + marker, 1)

    if text == original:
        return False

    path.write_text(f"{PATCH_MARKER}\n{text}", encoding="utf-8")
    return True


def _patch_capture_manager(path: Path) -> bool:
    if not path.is_file():
        return False

    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        return False

    original = text
    replacements = [
        (
            '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", timeout_seconds=60,
                           output_path=""):
''',
            '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", timeout_seconds=60,
                           output_path="", target_process_name="", connect_target=True):
''',
        ),
        (
            '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", timeout_seconds=60,
                           output_path="", target_process_name=""):
''',
            '''    def launch_application(self, exe_path, working_dir="", cmd_line="",
                           graphics_api="auto", timeout_seconds=60,
                           output_path="", target_process_name="", connect_target=True):
''',
        ),
        (
            "        target = self._connect_target(create_target_control, ident, timeout_seconds)\n",
            "        target = self._connect_target(\n            create_target_control, ident, timeout_seconds,\n            target_process_name, graphics_api)\n",
        ),
        (
            '''        pid = self._get_target_pid(target)
        session_id = uuid.uuid4().hex
''',
            '''        pid = self._get_target_pid(target)
        target_name = self._get_target_name(target)
        target_api = self._get_target_api(target)
        session_id = uuid.uuid4().hex
''',
        ),
        (
            '''            "pid": pid,
            "ident": ident,
''',
            '''            "pid": pid,
            "ident": ident,
            "target_name": target_name,
            "target_api": target_api,
''',
        ),
        (
            '''            "pid": pid,
            "ident": ident,
            "exe_path": exe_path,
''',
            '''            "pid": pid,
            "ident": ident,
            "target_name": target_name,
            "target_api": target_api,
            "exe_path": exe_path,
''',
        ),
        (
            '''            "ident": session.get("ident", 0),
            "exe_path": session.get("exe_path", ""),
''',
            '''            "ident": session.get("ident", 0),
            "target_name": self._get_target_name(target) or session.get("target_name", ""),
            "target_api": self._get_target_api(target) or session.get("target_api", ""),
            "exe_path": session.get("exe_path", ""),
''',
        ),
    ]
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)

    if "if not self._as_bool(connect_target):" not in text:
        marker = "        target = self._connect_target(\n"
        if marker in text:
            text = text.replace(marker, _LAUNCH_DETACHED_BLOCK + marker, 1)

    if "def connect_running_target" not in text:
        marker = "    def get_target_status(self, session_id):\n"
        if marker in text:
            text = text.replace(marker, _CAPTURE_MANAGER_CONNECT_METHODS + marker, 1)

    text = _replace_connect_target_method(text)
    if text == original:
        return False

    path.write_text(f"{PATCH_MARKER}\n{text}", encoding="utf-8")
    return True


def _replace_connect_target_method(text: str) -> str:
    start = text.find("    def _connect_target(")
    end = text.find("    def _wait_for_capture_file(", start)
    if start == -1 or end == -1:
        return text
    return text[:start] + _CONNECT_TARGET_METHODS + text[end:]


_QT_DISPATCHER_CODE = '''try:
    from PySide2 import QtCore, QtWidgets
except Exception:
    QtCore = None
    QtWidgets = None


if QtCore is not None:
    class QtMainThreadDispatcher(QtCore.QObject):
        run_signal = QtCore.Signal(object)

        def __init__(self):
            super(QtMainThreadDispatcher, self).__init__()
            self.run_signal.connect(self._run, QtCore.Qt.QueuedConnection)

        def call(self, fn, *args, **kwargs):
            app = QtWidgets.QApplication.instance() if QtWidgets is not None else None
            if app is not None and QtCore.QThread.currentThread() == app.thread():
                return fn(*args, **kwargs)

            request = {
                "fn": fn,
                "args": args,
                "kwargs": kwargs,
                "event": threading.Event(),
                "result": None,
                "error": None,
            }
            self.run_signal.emit(request)
            if not request["event"].wait(300.0):
                raise TimeoutError("Timed out waiting for RenderDoc UI thread")
            if request["error"] is not None:
                raise request["error"]
            return request["result"]

        @QtCore.Slot(object)
        def _run(self, request):
            try:
                request["result"] = request["fn"](*request["args"], **request["kwargs"])
            except Exception as e:
                request["error"] = e
            finally:
                request["event"].set()
else:
    class QtMainThreadDispatcher(object):
        def call(self, fn, *args, **kwargs):
            return fn(*args, **kwargs)
'''


_REQUEST_LAUNCH_ORIGINAL = '''        return self.facade.launch_application(
            exe_path,
            params.get("working_dir", params.get("workingDir", "")),
            params.get("cmd_line", params.get("cmdLine", "")),
            params.get("graphics_api", params.get("graphicsApi", "auto")),
        )
'''


_REQUEST_LAUNCH_V1 = '''        return self.facade.launch_application(
            exe_path,
            params.get("working_dir", params.get("workingDir", "")),
            params.get("cmd_line", params.get("cmdLine", "")),
            params.get("graphics_api", params.get("graphicsApi", "auto")),
            params.get(
                "target_process_name",
                params.get("targetProcessName", params.get("target_name", params.get("targetName", ""))),
            ),
        )
'''


_REQUEST_LAUNCH_V2 = '''        return self.facade.launch_application(
            exe_path,
            params.get("working_dir", params.get("workingDir", "")),
            params.get("cmd_line", params.get("cmdLine", "")),
            params.get("graphics_api", params.get("graphicsApi", "auto")),
            params.get(
                "target_process_name",
                params.get("targetProcessName", params.get("target_name", params.get("targetName", ""))),
            ),
            params.get("connect_target", params.get("connectTarget", True)),
        )
'''


_REQUEST_HANDLER_CONNECT_METHODS = '''    def _handle_connect_running_target(self, params):
        """Handle connect_running_target request"""
        return self.facade.connect_running_target(
            params.get(
                "target_process_name",
                params.get("targetProcessName", params.get("target_name", params.get("targetName", ""))),
            ),
            params.get("graphics_api", params.get("graphicsApi", "auto")),
            int(params.get("timeout_seconds", params.get("timeoutSeconds", 60))),
        )

    def _handle_list_running_targets(self, params):
        """Handle list_running_targets request"""
        return self.facade.list_running_targets()

'''


_FACADE_CONNECT_METHODS = '''    def connect_running_target(self, target_process_name="", graphics_api="auto",
                               timeout_seconds=60):
        """Connect TargetControl to an already-running RenderDoc target"""
        return self._capture.connect_running_target(
            target_process_name, graphics_api, timeout_seconds)

    def list_running_targets(self):
        """List active RenderDoc targets visible from localhost"""
        return self._capture.list_running_targets()

'''


_LAUNCH_DETACHED_BLOCK = '''        if not self._as_bool(connect_target):
            return {
                "session_id": "",
                "pid": 0,
                "ident": ident,
                "exe_path": exe_path,
                "working_dir": working_dir,
                "cmd_line": cmd_line or "",
                "graphics_api": graphics_api,
                "status": "launched",
                "controllable": False,
                "connected": False,
            }

'''


_CAPTURE_MANAGER_CONNECT_METHODS = '''    def connect_running_target(self, target_process_name="", graphics_api="auto",
                               timeout_seconds=60):
        """Connect TargetControl to an already-running RenderDoc target."""
        create_target_control = self._get_target_control_entrypoint(
            "connect_running_target")
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
                if expected_name and not self._target_name_matches(
                        info.get("target_name", ""), expected_name):
                    self._shutdown_target(target)
                    continue
                if not self._target_api_matches(info.get("target_api", ""), expected_api):
                    self._shutdown_target(target)
                    continue

                session_id = uuid.uuid4().hex
                self._target_sessions[session_id] = {
                    "session_id": session_id,
                    "target": target,
                    "pid": info.get("pid", 0),
                    "ident": ident,
                    "target_name": info.get("target_name", ""),
                    "target_api": info.get("target_api", ""),
                    "exe_path": info.get("target_name", "") or expected_name,
                    "working_dir": "",
                    "cmd_line": "",
                    "graphics_api": expected_api,
                    "started_at": time.time(),
                    "last_capture_path": "",
                }
                info.update({
                    "session_id": session_id,
                    "status": "running",
                    "controllable": not self._target_disconnected(target),
                    "connected": not self._target_disconnected(target),
                })
                return info

            time.sleep(1.0)

        raise ValueError(
            "No running RenderDoc target matched %s with API %s. Visible targets: %s"
            % (expected_name or "<any>", expected_api, self._format_targets(last_targets)))

    def list_running_targets(self):
        """List active RenderDoc targets visible from localhost."""
        create_target_control = self._get_target_control_entrypoint(
            "list_running_targets")
        targets = []
        for ident in self._candidate_target_idents(0, ""):
            target = self._connect_target_candidate(create_target_control, ident)
            if target is None:
                continue
            targets.append(self._describe_target(target, ident))
            self._shutdown_target(target)
        return {"targets": targets, "count": len(targets)}

    def _get_target_control_entrypoint(self, tool_name):
        create_target_control = (
            getattr(rd, "CreateTargetControl", None)
            or getattr(rd, "RENDERDOC_CreateTargetControl", None)
        )
        if create_target_control is None:
            raise ValueError(
                "This RenderDoc Python build does not expose CreateTargetControl; "
                "%s is unavailable" % tool_name)
        return create_target_control

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
            parts.append(
                "ident=%s pid=%s name=%s api=%s connected=%s"
                % (
                    target.get("ident", ""),
                    target.get("pid", ""),
                    target.get("target_name", ""),
                    target.get("target_api", ""),
                    target.get("connected", ""),
                )
            )
        return "; ".join(parts)

    def _as_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in ("0", "false", "no", "off")
        return bool(value)

'''


_CONNECT_TARGET_METHODS = '''    def _connect_target(self, create_target_control, ident, timeout_seconds,
                        target_process_name="", graphics_api="auto"):
        expected_name = (target_process_name or "").strip()
        expected_api = self._normalize_graphics_api(graphics_api)
        fallback_target = None
        fallback_ident = 0
        deadline = time.time() + max(float(timeout_seconds), 5.0)

        while time.time() < deadline:
            candidate_idents = self._candidate_target_idents(ident, expected_name)
            for candidate in candidate_idents:
                if candidate <= 0:
                    continue
                if fallback_target is not None and candidate == fallback_ident:
                    continue

                target = self._connect_target_candidate(create_target_control, candidate)
                if target is None:
                    continue

                target_name = self._get_target_name(target)
                target_api = self._get_target_api(target)
                if expected_name and not self._target_name_matches(target_name, expected_name):
                    self._shutdown_target(target)
                    continue

                if not expected_name:
                    return target

                if self._target_api_matches(target_api, expected_api):
                    if fallback_target is not None:
                        self._shutdown_target(fallback_target)
                    return target

                if fallback_target is None:
                    fallback_target = target
                    fallback_ident = candidate
                else:
                    self._shutdown_target(target)

            if fallback_target is not None:
                if self._target_disconnected(fallback_target):
                    fallback_target = None
                    fallback_ident = 0
                elif self._target_api_matches(
                        self._get_target_api(fallback_target), expected_api):
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
        enumerate_targets = (
            getattr(rd, "EnumerateRemoteTargets", None)
            or getattr(rd, "RENDERDOC_EnumerateRemoteTargets", None)
        )
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
            return create_target_control("", int(ident), "renderdoc-mcp", True)
        except Exception:
            return None

    def _target_name_matches(self, target_name, expected_name):
        target = (target_name or "").lower()
        expected = (expected_name or "").lower()
        if not expected:
            return True
        names = [expected]
        if expected.endswith(".exe"):
            names.append(expected[:-4])
        else:
            names.append(expected + ".exe")
        return any(name and name in target for name in names)

    def _target_api_matches(self, target_api, expected_api):
        api = (target_api or "").lower()
        expected = (expected_api or "auto").lower()
        if not api:
            return False
        if expected in ("", "auto"):
            return True
        return expected in api

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

    def _shutdown_target(self, target):
        try:
            target.Shutdown()
        except Exception:
            pass

'''
