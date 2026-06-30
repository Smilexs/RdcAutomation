from __future__ import annotations

from pathlib import Path

import pytest

from rdc_auto.config import AppConfig, load_config, save_config
from rdc_auto.errors import DependencyMissing, UserActionRequired
from rdc_auto.operations import (
    OperationContext,
    check_environment,
    export_assets,
    release_session,
    restart_mcp,
    setup_renderdoc,
    setup_renderdoc_and_mcp,
    start_mcp,
    stop_mcp,
)


def test_cli_save_monkeypatch_does_not_pollute_direct_operation_save(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "session-1"
    cfg.capture.active_launch_id = "launch-1"
    cfg.capture.active_pid = 123
    cfg.capture.active_session_started_at = "2026-06-22T00:00:00+08:00"
    mumu_root = tmp_path / "MuMu"
    mumu_exe = mumu_root / "nx_main" / "MuMuNxMain.exe"
    mumu_exe.parent.mkdir(parents=True)
    mumu_exe.write_bytes(b"exe")
    cfg.emulator.root_dir = str(mumu_root)
    save_config(cfg)

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            self.config = config

        def attach(self, force=False, confirm_vulkan=False):
            return "launch-2"

    with monkeypatch.context() as cli_patch:
        cli_patch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
        cli_patch.setattr("rdc_auto.cli.load_config", lambda: cfg)
        cli_patch.setattr("rdc_auto.cli.save_config", lambda config: None)
        cli_patch.setattr("rdc_auto.cli._capture_bridge_client", lambda config, start_qrenderdoc: object())
        cli_patch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

        from rdc_auto.cli import main

        assert main(["attach", "--yes-vulkan"]) == 0

    release_session(OperationContext(config=None))

    saved = load_config()
    assert saved.capture.active_session_id is None
    assert saved.capture.active_launch_id == ""
    assert saved.capture.active_pid is None
    assert saved.capture.active_session_started_at is None


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


def test_restart_mcp_can_force_release_active_capture_session(monkeypatch):
    cfg = AppConfig.default()
    cfg.capture.active_launch_id = "launch-1"
    terminated = []

    monkeypatch.setattr("rdc_auto.operations.stop_standalone_mcp_bridge", lambda executable_path: terminated.append(executable_path))
    monkeypatch.setattr("rdc_auto.operations.is_process_running", lambda image_name: False)
    monkeypatch.setattr("rdc_auto.operations.start_mcp", lambda ctx: "client")

    client = restart_mcp(
        OperationContext(config=cfg, save_config_fn=lambda config: None),
        force_release_session=True,
    )

    assert client == "client"
    assert cfg.capture.active_session_id is None
    assert cfg.capture.active_launch_id == ""
    assert terminated == ["RenderDocMCP.exe"]


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


def test_export_assets_persists_source_rdc_path(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    rdc_path = tmp_path / "manual.rdc"
    output_dir = tmp_path / "out"
    saved = []

    class FakeExportService:
        def __init__(self, mcp):
            self.mcp = mcp

        def export(self, rdc_path_arg, output_dir_arg, assets):
            assert rdc_path_arg == rdc_path
            assert output_dir_arg == output_dir
            assert assets == "textures"
            return {"source_rdc": str(rdc_path_arg)}

    monkeypatch.setattr("rdc_auto.operations.mcp_client", lambda config: "mcp")
    monkeypatch.setattr("rdc_auto.operations.ExportService", FakeExportService)

    result = export_assets(
        OperationContext(config=cfg, save_config_fn=lambda config: saved.append(config.capture.last_rdc_path)),
        rdc_path=rdc_path,
        output_dir=output_dir,
        assets="textures",
    )

    assert result == {"source_rdc": str(rdc_path)}
    assert cfg.capture.last_rdc_path == str(rdc_path)
    assert saved == [str(rdc_path)]


def test_check_environment_rejects_invalid_configured_renderdoc_path(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(tmp_path / "missing" / "qrenderdoc.exe")

    with pytest.raises(DependencyMissing, match="Configured qrenderdoc.exe was not found"):
        check_environment(OperationContext(config=cfg))


def test_check_environment_rejects_invalid_configured_mcp_path(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    cfg.mcp.executable_path = str(tmp_path / "missing" / "RenderDocMCP.exe")

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            return False

    monkeypatch.setattr("rdc_auto.operations.RenderDocInstaller", FakeRenderDocInstaller)

    with pytest.raises(DependencyMissing, match="Configured RenderDocMCP executable was not found"):
        check_environment(OperationContext(config=cfg))


def test_setup_renderdoc_and_mcp_does_not_prompt_for_mumu(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    cfg = AppConfig.default()
    calls = []
    mcp_exe = tmp_path / "RenderDocMCP.exe"
    mcp_exe.write_bytes(b"exe")

    monkeypatch.setattr("rdc_auto.operations.setup_renderdoc", lambda ctx, save=True: calls.append(("renderdoc", save)))

    class FakeMcpInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            calls.append(("mcp", None))
            return mcp_exe

    monkeypatch.setattr("rdc_auto.operations.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.operations.ensure_mumu_root", lambda config: (_ for _ in ()).throw(AssertionError("auto tool install must not prompt for MuMu12")))

    setup_renderdoc_and_mcp(OperationContext(config=cfg))

    assert calls == [("renderdoc", False), ("mcp", None)]
    assert cfg.mcp.executable_path == str(mcp_exe)
    assert load_config().mcp.executable_path == str(mcp_exe)


def test_setup_renderdoc_with_configured_path_only_checks_that_path(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    cfg = AppConfig.default()
    qrenderdoc = tmp_path / "RenderDocCustom" / "qrenderdoc.exe"
    renderdoccmd = tmp_path / "RenderDocCustom" / "renderdoccmd.exe"
    qrenderdoc.parent.mkdir()
    qrenderdoc.write_bytes(b"exe")
    renderdoccmd.write_bytes(b"exe")
    cfg.renderdoc.qrenderdoc_path = str(qrenderdoc)

    class FakeMcpInstaller:
        def __init__(self, config):
            raise AssertionError("custom RenderDoc repair should not install MCP")

    monkeypatch.setattr("rdc_auto.operations.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.operations.ensure_mumu_root", lambda config: (_ for _ in ()).throw(AssertionError("custom RenderDoc repair should not prompt for MuMu12")))
    monkeypatch.setattr("rdc_auto.renderdoc_installer.RenderDocInstaller._read_installed_version", lambda self, found: "1.44")

    setup_renderdoc(OperationContext(config=cfg))

    assert cfg.renderdoc.install_dir == str(qrenderdoc.parent)
    assert cfg.renderdoc.qrenderdoc_path == str(qrenderdoc)
    assert cfg.renderdoc.renderdoccmd_path == str(renderdoccmd)
    assert load_config().renderdoc.qrenderdoc_path == str(qrenderdoc)


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
