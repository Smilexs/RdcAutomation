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
            return {"session_id": "s1", "pid": 1234}
        if method == "get_target_status":
            return {"alive": True, "connected": True, "can_capture": True}
        if method == "trigger_capture":
            return {"rdc_path": params["output_path"], "captured": True, "pid": 1234}
        return {"status": "ok"}


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


def test_attach_refuses_running_mumu_without_force(tmp_path):
    cfg = AppConfig.default()
    service = CaptureService(cfg, FakeMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=True))

    with pytest.raises(UserActionRequired):
        service.attach(force=False, confirm_vulkan=True)


def test_attach_terminates_running_mumu_with_force(tmp_path):
    cfg = AppConfig.default()
    mumu = FakeMumu(tmp_path / "MuMuNxMain.exe", running=True)
    mcp = FakeMcp()
    service = CaptureService(cfg, mcp, mumu)

    session = service.attach(force=True, confirm_vulkan=True)

    assert mumu.terminated is True
    assert session == "s1"
    assert cfg.capture.active_session_id == "s1"
    assert cfg.capture.active_session_started_at
    assert mcp.calls[0][0] == "launch_application"
    assert mcp.calls[0][1]["graphics_api"] == "vulkan"


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
    service = CaptureService(cfg, FakeMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    with pytest.raises(UserActionRequired):
        service.capture(tmp_path)


def test_capture_triggers_current_session(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "s1"
    service = CaptureService(cfg, FakeMcp(), FakeMumu(tmp_path / "MuMuNxMain.exe", running=False))

    rdc = service.capture(tmp_path)

    assert rdc.parent == tmp_path
    assert rdc.suffix == ".rdc"
    assert cfg.capture.last_rdc_path == str(rdc)


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
