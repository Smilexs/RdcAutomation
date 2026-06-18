from __future__ import annotations

import json
import sys
import threading
import time
import types

from rdc_auto.capture_bridge import CaptureBridgeClient, CaptureBridgeInstaller, EXTENSION_INIT, capture_bridge_ipc_dir


def test_capture_bridge_client_uses_independent_ipc_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TEMP", str(tmp_path))

    assert capture_bridge_ipc_dir() == tmp_path / "rdc_auto_capture_bridge"


def test_capture_bridge_client_writes_request_and_reads_response(tmp_path):
    ipc = tmp_path / "rdc_auto_capture_bridge"
    client = CaptureBridgeClient(ipc_dir=ipc, poll_interval=0.01, timeout=1.0)

    def responder():
        request_path = ipc / "request.json"
        response_path = ipc / "response.json"
        while not request_path.exists():
            time.sleep(0.01)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request_path.unlink()
        response_path.write_text(json.dumps({"id": request["id"], "result": {"status": "ok"}}), encoding="utf-8")

    thread = threading.Thread(target=responder)
    thread.start()
    result = client.call("ping")
    thread.join(timeout=1)

    assert result == {"status": "ok"}


def test_capture_bridge_installer_writes_extension_and_always_load(tmp_path):
    extension_root = tmp_path / "qrenderdoc" / "extensions"
    installer = CaptureBridgeInstaller(extension_root=extension_root)

    installed = installer.install()

    assert installed == extension_root / "rdc_auto_capture_bridge"
    assert (installed / "extension.json").is_file()
    assert (installed / "__init__.py").is_file()
    assert installer.bootstrap_script() == installed / "bootstrap.py"
    assert installer.bootstrap_script().is_file()
    bootstrap = installer.bootstrap_script().read_text(encoding="utf-8")
    assert "__file__" not in bootstrap
    assert json.dumps(str(installed / "__init__.py")) in bootstrap
    ui_config = json.loads((tmp_path / "qrenderdoc" / "UI.config").read_text(encoding="utf-8"))
    assert "rdc_auto_capture_bridge" in ui_config["AlwaysLoad_Extensions"]


def test_capture_bridge_matches_mumu_vmm_headless_alias(monkeypatch):
    namespace = _load_capture_bridge_extension(monkeypatch)
    controller = namespace["CaptureController"](ctx=None)

    assert controller._target_name_matches("MuMuVMMHeadless", "MuMuVMHeadless")
    assert controller._target_name_matches("MuMuVMHeadless", "MuMuVMMHeadless")


def test_capture_bridge_accepts_unknown_api_for_name_matched_target(monkeypatch):
    namespace = _load_capture_bridge_extension(monkeypatch)
    controller = namespace["CaptureController"](ctx=None)

    assert controller._target_api_matches_named_target("", "vulkan")
    assert controller._target_api_matches_named_target("Vulkan", "vulkan")
    assert not controller._target_api_matches_named_target("D3D11", "vulkan")


def test_capture_bridge_prefers_copy_capture_for_new_capture_id(monkeypatch, tmp_path):
    namespace = _load_capture_bridge_extension(monkeypatch)
    controller = namespace["CaptureController"](ctx=None)
    source = tmp_path / "renderdoc-temp.rdc"
    output = tmp_path / "capture.rdc"
    source.write_bytes(b"rdc")
    copied = []

    class NewCapture:
        path = str(source)
        ID = 7

    class Message:
        type = "NewCapture"
        newCapture = NewCapture()

    class Target:
        def __init__(self):
            self.messages = [Message()]

        def ReceiveMessage(self, *args):
            return self.messages.pop(0) if self.messages else None

        def Connected(self):
            return True

    controller._copy_capture = lambda target, capture_id, output_path: copied.append((capture_id, output_path)) or str(output)

    result = controller._wait_for_capture_file(Target(), "MuMuVMMHeadless", str(tmp_path / "template"), str(output), 5)

    assert result == str(output)
    assert copied == [(7, str(output))]


def test_capture_bridge_retries_copying_locked_capture_file(monkeypatch, tmp_path):
    namespace = _load_capture_bridge_extension(monkeypatch)
    controller = namespace["CaptureController"](ctx=None)
    source = tmp_path / "renderdoc-temp.rdc"
    output = tmp_path / "capture.rdc"
    source.write_bytes(b"rdc")
    attempts = []

    def copyfile(src, dst):
        attempts.append((src, dst))
        if len(attempts) == 1:
            raise PermissionError("locked")
        output.write_bytes(b"copied")

    monkeypatch.setattr(namespace["shutil"], "copyfile", copyfile)

    result = controller._copy_capture_file(str(source), str(output), timeout_seconds=1.0)

    assert result == str(output)
    assert len(attempts) == 2
    assert output.read_bytes() == b"copied"


def _load_capture_bridge_extension(monkeypatch):
    fake_renderdoc = types.SimpleNamespace()
    fake_qrenderdoc = types.SimpleNamespace(WindowMenu=types.SimpleNamespace(Tools=object()))
    monkeypatch.setitem(sys.modules, "renderdoc", fake_renderdoc)
    monkeypatch.setitem(sys.modules, "qrenderdoc", fake_qrenderdoc)
    namespace = {"__name__": "test_capture_bridge_extension"}
    exec(EXTENSION_INIT, namespace)
    return namespace
