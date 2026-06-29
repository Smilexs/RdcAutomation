from __future__ import annotations

from pathlib import Path

import pytest

from rdc_auto.capture import CaptureService
from rdc_auto.config import AppConfig
from rdc_auto.errors import UserActionRequired


class FakeMcp:
    def __init__(self):
        self.calls = []

    def call(self, method, params=None, timeout=None):
        self.calls.append((method, params or {}, timeout))
        if method == "launch_application":
            return {"session_id": "s1", "ident": 99, "pid": 1234}
        if method == "connect_running_target":
            return {
                "session_id": "s-running",
                "pid": 5678,
                "target_name": "MuMuVMHeadless",
                "target_api": "Vulkan",
            }
        if method == "get_target_status":
            return {"alive": True, "connected": True, "can_capture": True}
        if method == "trigger_capture":
            return {"rdc_path": params["output_path"], "captured": True, "pid": 1234}
        return {"status": "ok"}


class BridgeStatusMcp(FakeMcp):
    def call(self, method, params=None, timeout=None):
        self.calls.append((method, params or {}, timeout))
        if method == "get_target_status":
            return {
                "session_id": params["session_id"],
                "exists": True,
                "controllable": True,
                "connected": True,
                "status": "running",
            }
        if method == "trigger_capture":
            return {"capture_path": params["output_path"], "status": "captured"}
        return super().call(method, params, timeout)


class FailingCloseMcp(FakeMcp):
    def call(self, method, params=None, timeout=None):
        self.calls.append((method, params or {}, timeout))
        if method == "close_target":
            raise RuntimeError("close failed")
        return {"status": "ok"}


class FakeMumu:
    def __init__(self, exe: Path, running: bool):
        self._exe = exe
        self._running = running
        self.terminated = False

    def executable(self):
        return self._exe

    def is_running(self):
        return self._running

    def terminate(self):
        self.terminated = True
        self._running = False

    def target_process_name(self):
        return "MuMuVMHeadless"


class FakeLaunchSpecMumu(FakeMumu):
    def __init__(self, exe: Path, running: bool, launch_exe: Path, cmd_line: str):
        super().__init__(exe, running)
        self._launch_exe = launch_exe
        self._cmd_line = cmd_line

    def launch_spec(self):
        return {
            "exe_path": self._launch_exe,
            "working_dir": self._launch_exe.parent,
            "cmd_line": self._cmd_line,
        }


class WaitableFakeMumu(FakeMumu):
    def __init__(self, exe: Path, running: bool):
        super().__init__(exe, running)
        self.waited_timeout = None

    def wait_until_running(self, timeout_seconds: float):
        self.waited_timeout = timeout_seconds
        self._running = True


def test_attach_refuses_running_mumu_without_force(tmp_path):
    cfg = AppConfig.default()
    service = CaptureService(cfg, FakeMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=True))

    with pytest.raises(UserActionRequired):
        service.attach(force=False, confirm_vulkan=True)


def test_attach_terminates_running_mumu_with_force(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "old-session"
    cfg.capture.active_pid = 99
    mumu = FakeMumu(tmp_path / "MuMuNxMain.exe", running=True)
    mcp = FakeMcp()
    service = CaptureService(cfg, mcp, mumu)

    launch_id = service.attach(force=True, confirm_vulkan=True)

    assert mumu.terminated is True
    assert launch_id == "99"
    assert cfg.capture.active_session_id is None
    assert cfg.capture.active_pid is None
    assert cfg.capture.active_session_started_at is None
    assert mcp.calls[0][0] == "launch_application"
    assert mcp.calls[0][1]["graphics_api"] == "vulkan"
    assert mcp.calls[0][1]["connect_target"] is False


def test_attach_uses_emulator_launch_spec(tmp_path):
    cfg = AppConfig.default()
    mcp = FakeMcp()
    launcher = tmp_path / "mumu-cli.exe"
    service = CaptureService(
        cfg,
        mcp,
        FakeLaunchSpecMumu(
            tmp_path / "MuMuNxMain.exe",
            running=False,
            launch_exe=launcher,
            cmd_line="control --vmindex 1 launch",
        ),
    )

    service.attach(force=False, confirm_vulkan=True)

    assert mcp.calls[0][1]["exe_path"] == str(launcher)
    assert mcp.calls[0][1]["working_dir"] == str(tmp_path)
    assert mcp.calls[0][1]["cmd_line"] == "control --vmindex 1 launch"


def test_attach_waits_for_emulator_process_after_renderdoc_launch(tmp_path):
    cfg = AppConfig.default()
    mcp = FakeMcp()
    mumu = WaitableFakeMumu(tmp_path / "MuMuNxMain.exe", running=False)
    service = CaptureService(cfg, mcp, mumu)

    service.attach(force=False, confirm_vulkan=True)

    assert mumu.waited_timeout == 60.0


def test_attach_does_not_connect_mumu_headless_target(tmp_path):
    cfg = AppConfig.default()
    mcp = FakeMcp()
    service = CaptureService(cfg, mcp, FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    service.attach(force=False, confirm_vulkan=True)

    assert "target_process_name" not in mcp.calls[0][1]
    assert mcp.calls[0][1]["connect_target"] is False


def test_attach_confirms_vulkan_before_force_terminating_mumu(tmp_path):
    cfg = AppConfig.default()
    mumu = FakeMumu(tmp_path / "MuMuNxMain.exe", running=True)
    mcp = FakeMcp()
    service = CaptureService(cfg, mcp, mumu)

    with pytest.raises(UserActionRequired):
        service.attach(force=True, confirm_vulkan=False)

    assert mumu.terminated is False
    assert mcp.calls == []


def test_capture_requires_active_session(tmp_path):
    cfg = AppConfig.default()
    mcp = FakeMcp()
    service = CaptureService(cfg, mcp, FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    rdc = service.capture(tmp_path)

    assert rdc.parent == tmp_path
    assert mcp.calls[0][0] == "connect_running_target"
    assert mcp.calls[0][1]["target_process_name"] == "MuMuVMHeadless"
    assert mcp.calls[0][1]["graphics_api"] == "vulkan"
    assert cfg.capture.active_session_id == "s-running"
    assert cfg.capture.active_pid == 5678


def test_capture_triggers_current_session(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "s1"
    service = CaptureService(cfg, FakeMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    rdc = service.capture(tmp_path)

    assert rdc.parent == tmp_path
    assert rdc.suffix == ".rdc"
    assert cfg.capture.last_rdc_path == str(rdc)


def test_capture_accepts_renderdoc_bridge_target_status(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "s1"
    mcp = BridgeStatusMcp()
    service = CaptureService(cfg, mcp, FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    rdc = service.capture(tmp_path)

    methods = [call[0] for call in mcp.calls]
    assert methods == ["get_target_status", "trigger_capture"]
    assert rdc.parent == tmp_path
    assert rdc.suffix == ".rdc"


class DisconnectedThenConnectMcp(FakeMcp):
    def call(self, method, params=None, timeout=None):
        self.calls.append((method, params or {}, timeout))
        if method == "get_target_status":
            return {"exists": False, "controllable": False, "status": "not_found"}
        if method == "connect_running_target":
            return {"session_id": "new-session", "pid": 8765, "target_name": "MuMuVMHeadless"}
        if method == "trigger_capture":
            return {"rdc_path": params["output_path"], "captured": True}
        return super().call(method, params, timeout)


def test_capture_reconnects_when_saved_session_is_stale(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "stale"
    mcp = DisconnectedThenConnectMcp()
    service = CaptureService(cfg, mcp, FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    service.capture(tmp_path)

    assert [call[0] for call in mcp.calls] == ["get_target_status", "connect_running_target", "trigger_capture"]
    assert cfg.capture.active_session_id == "new-session"
    assert cfg.capture.active_pid == 8765


def test_close_clears_active_state_when_mcp_close_fails(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "s1"
    cfg.capture.active_pid = 1234
    service = CaptureService(cfg, FailingCloseMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    with pytest.raises(RuntimeError):
        service.close()

    assert cfg.capture.active_session_id is None
    assert cfg.capture.active_pid is None
    assert cfg.capture.active_session_started_at is None
