from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rdc_auto.config import AppConfig
from rdc_auto.errors import McpCapabilityMissing, UserActionRequired
from rdc_auto.prompts import choose_option, prompt_path
from rdc_auto.cli import build_parser, main


def test_package_exposes_version():
    import rdc_auto

    assert isinstance(rdc_auto.__version__, str)
    assert rdc_auto.__version__


def test_main_module_can_run_as_script():
    main_module = Path(__file__).parents[1] / "rdc_auto" / "__main__.py"

    result = subprocess.run(
        [sys.executable, str(main_module), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "setup" in result.stdout


def test_choose_option_accepts_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert choose_option("Asset type", ["textures", "meshes", "both"], default="both") == "both"


def test_choose_option_accepts_number(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "2")

    assert choose_option("Asset type", ["textures", "meshes", "both"], default="both") == "meshes"


def test_prompt_path_returns_default(monkeypatch, tmp_path):
    default = tmp_path / "captures"
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert prompt_path("Output directory", default=default) == default


def test_parser_accepts_short_commands():
    parser = build_parser()

    assert parser.parse_args(["setup"]).command == "setup"
    assert parser.parse_args(["attach"]).command == "attach"
    assert parser.parse_args(["capture"]).command == "capture"
    assert parser.parse_args(["export"]).command == "export"


def test_attach_parser_accepts_vm_index():
    parser = build_parser()
    args = parser.parse_args(["attach", "--vm-index", "1"])

    assert args.vm_index == "1"


def test_capture_parser_accepts_out():
    parser = build_parser()
    args = parser.parse_args(["capture", "--out", "D:\\Captures"])

    assert args.out == "D:\\Captures"


def test_export_parser_accepts_assets_and_out():
    parser = build_parser()
    args = parser.parse_args(["export", "D:\\a.rdc", "--assets", "textures", "--out", "D:\\Exports"])

    assert args.rdc_path == "D:\\a.rdc"
    assert args.assets == "textures"
    assert args.out == "D:\\Exports"


def test_main_returns_error_when_config_load_fails(monkeypatch):
    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)

    def fail_load_config():
        raise RuntimeError("boom")

    monkeypatch.setattr("rdc_auto.cli.load_config", fail_load_config)

    assert main(["setup"]) == 1


def test_setup_fails_when_renderdoc_missing_after_install(monkeypatch, capsys):
    cfg = AppConfig.default()
    cfg.emulator.root_dir = "D:\\MuMu"

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            return False

        def resolve_download_url(self):
            return "https://example/RenderDoc.exe"

        def download_installer(self, url):
            return Path("D:\\Downloads\\RenderDoc.exe")

        def run_installer(self, installer_path):
            return None

    class FakeMcpInstaller:
        def __init__(self, config):
            self.config = config

        def runtime_executable(self):
            return Path("D:\\RenderDocMCP.exe")

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.validate_mumu_root", lambda root: Path("D:\\MuMu\\MuMuPlayer-12.0\\nx_main\\MuMuNxMain.exe"))
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)

    assert main(["setup"]) == 1
    assert "setup complete" not in capsys.readouterr().out


def test_setup_does_not_persist_invalid_prompted_mumu_root(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
    saved_roots = []

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            return True

    class FakeMcpInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            return Path("D:\\RenderDocMCP.exe")

    bad_root = tmp_path / "bad"

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: saved_roots.append(config.emulator.root_dir))
    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.prompt_path", lambda label: bad_root)

    assert main(["setup"]) == 1
    assert cfg.emulator.root_dir == ""
    assert saved_roots == [""]


def test_attach_reprompts_when_configured_mumu_root_is_invalid(monkeypatch, tmp_path):
    good_root = tmp_path / "good"
    exe = good_root / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path / "bad")
    calls = []

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            self.config = config

        def attach(self, force=False, confirm_vulkan=False):
            calls.append(("attach", self.config.emulator.root_dir))
            return "s1"

    monkeypatch.setattr("rdc_auto.cli._capture_bridge_client", lambda config, start_qrenderdoc: object())
    monkeypatch.setattr("rdc_auto.cli.prompt_path", lambda label: good_root)
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)

    from rdc_auto.cli import _cmd_attach

    _cmd_attach(cfg, force=False, yes_vulkan=True)

    assert cfg.emulator.root_dir == str(good_root)
    assert calls == [("attach", str(good_root))]


def test_main_saves_expected_error_config_mutations(monkeypatch):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "s1"
    saved_sessions = []

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            self.config.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
            return True

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            self.config = config
            self.mcp = mcp
            self.mumu = mumu

        def capture(self, output_dir, timeout_seconds=60):
            raise UserActionRequired("No active RenderDoc target session. Run rdc-auto attach first.")

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: saved_sessions.append(config.capture.active_session_id))
    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli._capture_bridge_client", lambda config, start_qrenderdoc: object())
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["capture", "--out", "D:\\Captures"]) == 2
    assert saved_sessions == ["s1"]


def test_attach_prepares_capture_bridge_and_qrenderdoc_before_launch(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    mumu_root = tmp_path / "MuMu"
    mumu_exe = mumu_root / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    mumu_exe.parent.mkdir(parents=True)
    mumu_exe.write_bytes(b"exe")
    cfg.emulator.root_dir = str(mumu_root)
    calls = []

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            self.config = config

        def attach(self, force=False, confirm_vulkan=False):
            calls.append("attach")
            return "s1"

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli._capture_bridge_client", lambda config, start_qrenderdoc: calls.append(("bridge", start_qrenderdoc)) or object())
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["attach", "--yes-vulkan"]) == 0
    assert calls == [("bridge", True), "attach"]


def test_attach_does_not_use_renderdoc_mcp(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    mumu_root = tmp_path / "MuMu"
    mumu_exe = mumu_root / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    mumu_exe.parent.mkdir(parents=True)
    mumu_exe.write_bytes(b"exe")
    cfg.emulator.root_dir = str(mumu_root)
    bridge_starts = []

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            pass

        def attach(self, force=False, confirm_vulkan=False):
            return "s1"

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli._capture_bridge_client", lambda config, start_qrenderdoc: bridge_starts.append(start_qrenderdoc) or object())
    monkeypatch.setattr("rdc_auto.cli._mcp_client", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("attach must not use RenderDocMCP")))
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["attach", "--yes-vulkan"]) == 0
    assert bridge_starts == [True]


def test_runtime_ready_does_not_download_or_install_mcp(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"
    cfg.mcp.executable_path = str(tmp_path / "RenderDocMCP.exe")
    Path(cfg.mcp.executable_path).write_bytes(b"exe")

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            self.config.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
            return True

    class NoSetupMcpInstaller:
        def __init__(self, config):
            self.config = config

        def runtime_executable(self):
            return Path(self.config.mcp.executable_path)

        def ensure_installed(self):
            raise AssertionError("non-setup commands must not run MCP installer")

    class FakeMcpClient:
        def __init__(self, executable_path=None, **kwargs):
            self.executable_path = executable_path

        def ping(self):
            return True

        def call(self, method, params=None, timeout=None):
            return {"targets": [], "count": 0}

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", NoSetupMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", FakeMcpClient)
    monkeypatch.setattr("rdc_auto.cli._stop_standalone_mcp_bridge", lambda executable_path: None)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: None)

    assert _mcp_client_for_test(monkeypatch, cfg).executable_path is None
    assert Path(cfg.mcp.executable_path) == Path(tmp_path / "RenderDocMCP.exe")


def test_mcp_client_uses_qrenderdoc_bridge_without_starting_runtime_executable(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"
    constructed = []

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

    class FakeMcpClient:
        def __init__(self, executable_path=None, **kwargs):
            constructed.append(executable_path)

        def ping(self):
            return True

        def call(self, method, params=None, timeout=None):
            return {"targets": [], "count": 0}

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", FakeMcpClient)
    monkeypatch.setattr("rdc_auto.cli._stop_standalone_mcp_bridge", lambda executable_path: None)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: None)

    _mcp_client_for_test(monkeypatch, cfg)

    assert constructed == [None]
    assert cfg.mcp.executable_path == str(exe)


def test_mcp_client_patches_renderdoc_mcp_before_starting_qrenderdoc(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"
    calls = []

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            self.config.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
            calls.append("renderdoc")
            return True

    class FakeMcpInstaller:
        def __init__(self, config):
            self.config = config

        def runtime_executable(self):
            calls.append("mcp")
            return exe

    class FakeMcpClient:
        def __init__(self, executable_path=None, **kwargs):
            pass

        def ping(self):
            calls.append("ping")
            return True

        def call(self, method, params=None, timeout=None):
            raise AssertionError("generic MCP client setup must not check capture-only methods")

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.patch_renderdoc_mcp_extension", lambda path: calls.append(("patch", path)) or False)
    monkeypatch.setattr("rdc_auto.cli._stop_standalone_mcp_bridge", lambda executable_path: calls.append(("stop_mcp", executable_path)))
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", FakeMcpClient)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: calls.append("qrenderdoc"))

    _mcp_client_for_test(monkeypatch, cfg)

    assert calls == ["renderdoc", "mcp", ("patch", exe), ("stop_mcp", exe), "qrenderdoc", "ping"]


def test_mcp_client_stops_standalone_bridge_before_capability_check(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    exe = tmp_path / "renderdoc-mcp.exe"
    exe.write_bytes(b"exe")
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"
    calls = []

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            self.config.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
            calls.append("renderdoc")
            return True

    class FakeMcpInstaller:
        def __init__(self, config):
            self.config = config

        def runtime_executable(self):
            calls.append("mcp")
            return exe

    class FakeMcpClient:
        def __init__(self, executable_path=None, **kwargs):
            pass

        def ping(self):
            calls.append("ping")
            return True

        def call(self, method, params=None, timeout=None):
            calls.append(method)
            return {"targets": [], "count": 0}

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.patch_renderdoc_mcp_extension", lambda path: calls.append(("patch", path)) or False)
    monkeypatch.setattr("rdc_auto.cli._stop_standalone_mcp_bridge", lambda executable_path: calls.append(("stop_mcp", executable_path)))
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: calls.append("qrenderdoc"))
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", FakeMcpClient)

    _mcp_client_for_test(monkeypatch, cfg, require_capture_connect=True)

    assert calls == [
        "renderdoc",
        "mcp",
        ("patch", exe),
        ("stop_mcp", exe),
        "qrenderdoc",
        "ping",
        "list_running_targets",
    ]


def test_mcp_client_requires_renderdoc_restart_after_runtime_patch(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"

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

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.patch_renderdoc_mcp_extension", lambda path: True)
    monkeypatch.setattr("rdc_auto.cli._process_is_running", lambda image_name: image_name == "qrenderdoc.exe")
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: (_ for _ in ()).throw(AssertionError("qrenderdoc must be restarted first")))

    with pytest.raises(UserActionRequired, match="Close all RenderDoc windows"):
        _mcp_client_for_test(monkeypatch, cfg)

    assert cfg.mcp.extension_patch_restart_required is True


def test_mcp_client_keeps_requiring_restart_until_qrenderdoc_is_closed(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"
    cfg.mcp.extension_patch_restart_required = True

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

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.patch_renderdoc_mcp_extension", lambda path: False)
    monkeypatch.setattr("rdc_auto.cli._process_is_running", lambda image_name: image_name == "qrenderdoc.exe")
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: (_ for _ in ()).throw(AssertionError("qrenderdoc must be restarted first")))

    with pytest.raises(UserActionRequired, match="Close all RenderDoc windows"):
        _mcp_client_for_test(monkeypatch, cfg)


def test_mcp_client_clears_restart_requirement_after_qrenderdoc_is_closed(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"
    cfg.mcp.extension_patch_restart_required = True

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

    class FakeMcpClient:
        def __init__(self, executable_path=None, **kwargs):
            pass

        def ping(self):
            return True

        def call(self, method, params=None, timeout=None):
            return {"targets": [], "count": 0}

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.patch_renderdoc_mcp_extension", lambda path: False)
    monkeypatch.setattr("rdc_auto.cli._process_is_running", lambda image_name: False)
    monkeypatch.setattr("rdc_auto.cli._stop_standalone_mcp_bridge", lambda executable_path: None)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", FakeMcpClient)

    _mcp_client_for_test(monkeypatch, cfg)

    assert cfg.mcp.extension_patch_restart_required is False


def test_mcp_client_reports_restart_when_loaded_extension_lacks_capture_connect(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"

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

    class OldExtensionMcpClient:
        def __init__(self, executable_path=None, **kwargs):
            pass

        def ping(self):
            return True

        def call(self, method, params=None, timeout=None):
            raise McpCapabilityMissing(f"Method not found: {method}")

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.patch_renderdoc_mcp_extension", lambda path: False)
    monkeypatch.setattr("rdc_auto.cli._stop_standalone_mcp_bridge", lambda executable_path: None)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", OldExtensionMcpClient)

    with pytest.raises(UserActionRequired, match="Close all RenderDoc windows"):
        _mcp_client_for_test(monkeypatch, cfg, require_capture_connect=True)


def _mcp_client_for_test(monkeypatch, cfg, require_capture_connect=False):
    from rdc_auto.cli import _mcp_client

    return _mcp_client(cfg, require_capture_connect=require_capture_connect)


def test_start_qrenderdoc_reuses_existing_process(monkeypatch, tmp_path):
    from rdc_auto.cli import _start_qrenderdoc

    qrenderdoc = tmp_path / "qrenderdoc.exe"
    qrenderdoc.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(qrenderdoc)
    popen_calls = []

    def runner(args, capture_output, text, check, **kwargs):
        return type(
            "Result",
            (),
            {"stdout": '"Image Name","PID"\n"qrenderdoc.exe","1234"\n'},
        )()

    monkeypatch.setattr("rdc_auto.cli.subprocess.run", runner)
    monkeypatch.setattr("rdc_auto.cli.subprocess.Popen", lambda args, **kwargs: popen_calls.append(args))

    _start_qrenderdoc(cfg)

    assert popen_calls == []


def test_start_qrenderdoc_refuses_multiple_instances(monkeypatch, tmp_path):
    from rdc_auto.cli import _start_qrenderdoc

    qrenderdoc = tmp_path / "qrenderdoc.exe"
    qrenderdoc.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(qrenderdoc)
    popen_calls = []

    def runner(args, capture_output, text, check, **kwargs):
        return type(
            "Result",
            (),
            {"stdout": '"Image Name","PID"\n"qrenderdoc.exe","1234"\n"qrenderdoc.exe","5678"\n'},
        )()

    monkeypatch.setattr("rdc_auto.cli.subprocess.run", runner)
    monkeypatch.setattr("rdc_auto.cli.subprocess.Popen", lambda args, **kwargs: popen_calls.append(args))

    with pytest.raises(UserActionRequired):
        _start_qrenderdoc(cfg)

    assert popen_calls == []


def test_process_count_parses_tasklist_without_english_header(monkeypatch):
    from rdc_auto.cli import _process_count

    def runner(args, capture_output, text, check, **kwargs):
        return type(
            "Result",
            (),
            {"stdout": '"映像名称","PID","会话名","会话#","内存使用"\n"qrenderdoc.exe","66844","Console","1","153,980 K"\n'},
        )()

    monkeypatch.setattr("rdc_auto.cli.subprocess.run", runner)

    assert _process_count("qrenderdoc.exe") == 1


def test_start_qrenderdoc_runs_python_bootstrap_when_provided(monkeypatch, tmp_path):
    from rdc_auto.cli import _start_qrenderdoc

    qrenderdoc = tmp_path / "qrenderdoc.exe"
    qrenderdoc.write_bytes(b"exe")
    bootstrap = tmp_path / "bootstrap.py"
    bootstrap.write_text("# bootstrap", encoding="utf-8")
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(qrenderdoc)
    popen_calls = []

    def runner(args, capture_output, text, check, **kwargs):
        return type("Result", (), {"stdout": '"Image Name","PID"\n'})()

    monkeypatch.setattr("rdc_auto.cli.subprocess.run", runner)
    monkeypatch.setattr("rdc_auto.cli.subprocess.Popen", lambda args, **kwargs: popen_calls.append(args))

    _start_qrenderdoc(cfg, python_script=bootstrap)

    assert popen_calls == [[str(qrenderdoc), "--python", str(bootstrap)]]


def test_capture_bridge_client_bootstraps_qrenderdoc_when_starting(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    bootstrap = tmp_path / "rdc_auto_capture_bridge" / "bootstrap.py"
    starts = []

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            self.config.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
            return True

    class FakeCaptureBridgeInstaller:
        def install(self):
            bootstrap.parent.mkdir(parents=True)
            bootstrap.write_text("# bootstrap", encoding="utf-8")
            return bootstrap.parent

        def bootstrap_script(self):
            return bootstrap

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.CaptureBridgeInstaller", FakeCaptureBridgeInstaller)
    monkeypatch.setattr("rdc_auto.cli._process_count", lambda image_name: 0)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config, python_script=None: starts.append(python_script))
    monkeypatch.setattr("rdc_auto.cli._wait_for_capture_bridge", lambda client: None)

    from rdc_auto.cli import _capture_bridge_client

    _capture_bridge_client(cfg, start_qrenderdoc=True)

    assert starts == [bootstrap]


def test_capture_connects_running_target_with_capture_bridge(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    mumu_root = tmp_path / "MuMu"
    mumu_exe = mumu_root / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    mumu_exe.parent.mkdir(parents=True)
    mumu_exe.write_bytes(b"exe")
    cfg.emulator.root_dir = str(mumu_root)
    output_dir = tmp_path / "captures"
    captured = []
    bridge_starts = []

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            self.config = config

        def capture(self, output_dir, timeout_seconds=60):
            captured.append((output_dir, timeout_seconds))
            return Path(output_dir) / "frame.rdc"

    def choose(label, options, default=None):
        raise AssertionError("capture must not prompt for attach when a running target can be connected")

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli._capture_bridge_client", lambda config, start_qrenderdoc: bridge_starts.append(start_qrenderdoc) or object())
    monkeypatch.setattr("rdc_auto.cli._mcp_client", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("capture must not use RenderDocMCP")))
    monkeypatch.setattr("rdc_auto.cli.choose_option", choose)
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["capture", "--out", str(output_dir)]) == 0
    assert captured == [(output_dir, 60)]
    assert bridge_starts == [False]


def test_capture_requires_existing_qrenderdoc(monkeypatch):
    cfg = AppConfig.default()

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            self.config.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
            return True

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.CaptureBridgeInstaller", lambda: type("Installer", (), {"install": lambda self: Path("bridge")})())
    monkeypatch.setattr("rdc_auto.cli._process_count", lambda image_name: 0)

    from rdc_auto.cli import _capture_bridge_client

    with pytest.raises(UserActionRequired, match="Run rdc-auto attach first"):
        _capture_bridge_client(cfg, start_qrenderdoc=False)


def test_capture_refuses_multiple_qrenderdoc_instances(monkeypatch):
    cfg = AppConfig.default()

    class FakeRenderDocInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            self.config.renderdoc.qrenderdoc_path = "D:\\RenderDoc\\qrenderdoc.exe"
            return True

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.CaptureBridgeInstaller", lambda: type("Installer", (), {"install": lambda self: Path("bridge")})())
    monkeypatch.setattr("rdc_auto.cli._process_count", lambda image_name: 2)

    from rdc_auto.cli import _capture_bridge_client

    with pytest.raises(UserActionRequired, match="Multiple qrenderdoc.exe instances"):
        _capture_bridge_client(cfg, start_qrenderdoc=False)


def test_main_reports_expected_file_errors_without_unexpected_prefix(monkeypatch, capsys):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "s1"

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            pass

        def capture(self, output_dir, timeout_seconds=60):
            raise FileNotFoundError("missing dependency")

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli._capture_bridge_client", lambda config, start_qrenderdoc: object())
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["capture", "--out", "D:\\Captures"]) == 1
    err = capsys.readouterr().err
    assert "missing dependency" in err
    assert "Unexpected error" not in err
