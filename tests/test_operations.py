from __future__ import annotations

from pathlib import Path

import pytest

from rdc_auto.config import AppConfig, load_config, save_config
from rdc_auto.errors import UserActionRequired
from rdc_auto.operations import OperationContext, check_environment, release_session, start_mcp, stop_mcp


def test_release_session_clears_capture_state(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "session-1"
    cfg.capture.active_launch_id = "launch-1"
    cfg.capture.active_pid = 123
    cfg.capture.active_session_started_at = "2026-06-22T00:00:00+08:00"

    release_session(OperationContext(config=cfg))

    assert cfg.capture.active_session_id is None
    assert cfg.capture.active_launch_id == ""
    assert cfg.capture.active_pid is None
    assert cfg.capture.active_session_started_at is None


def test_operation_context_uses_existing_config():
    cfg = AppConfig.default()
    ctx = OperationContext(config=cfg)

    assert ctx.config is cfg
    assert Path(ctx.config.mcp.install_dir).name == "mcp"


def test_release_session_without_config_persists_cleared_state(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "session-1"
    cfg.capture.active_launch_id = "launch-1"
    cfg.capture.active_pid = 123
    cfg.capture.active_session_started_at = "2026-06-22T00:00:00+08:00"
    save_config(cfg)

    release_session(OperationContext(config=None))

    saved = load_config()
    assert saved.capture.active_session_id is None
    assert saved.capture.active_launch_id == ""
    assert saved.capture.active_pid is None
    assert saved.capture.active_session_started_at is None


@pytest.mark.parametrize("field,value", [("active_session_id", "session-1"), ("active_launch_id", "launch-1")])
def test_stop_mcp_refuses_active_capture_session_before_terminate(monkeypatch, field, value):
    cfg = AppConfig.default()
    setattr(cfg.capture, field, value)
    terminated = []

    monkeypatch.setattr("rdc_auto.operations.stop_standalone_mcp_bridge", lambda executable_path: terminated.append(executable_path))
    monkeypatch.setattr("rdc_auto.operations.terminate_process_tree", lambda image_name: terminated.append(image_name))

    with pytest.raises(UserActionRequired, match="Active capture session exists"):
        stop_mcp(OperationContext(config=cfg))

    assert terminated == []


def test_check_environment_discovers_configured_mcp_executable(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    cfg = AppConfig.default()
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            return False

    class FakeMcpInstaller:
        def __init__(self, config):
            self.config = config

        def discover_executable(self, allow_configured=True):
            assert allow_configured is True
            return exe

        def runtime_executable(self):
            raise AssertionError("check_environment must not require setup metadata")

    monkeypatch.setattr("rdc_auto.operations.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.operations.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.operations.is_process_running", lambda image_name: False)

    result = check_environment(OperationContext(config=cfg))

    assert result["mcp_installed"] is True
    assert result["mcp_executable_path"] == str(exe)
    assert cfg.mcp.executable_path == str(exe)
    assert load_config().mcp.executable_path == str(exe)


def test_start_mcp_persists_restart_required_when_patch_requires_closed_renderdoc(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    cfg = AppConfig.default()
    save_config(cfg)
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            self.config.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
            return True

    class FakeMcpInstaller:
        def __init__(self, config):
            self.config = config

        def runtime_executable(self):
            return exe

    monkeypatch.setattr("rdc_auto.operations.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.operations.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.operations.is_process_running", lambda image_name: image_name == "qrenderdoc.exe")
    monkeypatch.setattr("rdc_auto.operations.patch_renderdoc_mcp_extension", lambda path: True)

    with pytest.raises(UserActionRequired, match="Close all RenderDoc windows"):
        start_mcp(OperationContext(config=None))

    saved = load_config()
    assert saved.mcp.executable_path == str(exe)
    assert saved.mcp.extension_patch_restart_required is True
