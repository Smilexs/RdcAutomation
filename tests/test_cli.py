from __future__ import annotations

from pathlib import Path

from rdc_auto.config import AppConfig
from rdc_auto.errors import UserActionRequired
from rdc_auto.prompts import choose_option, prompt_path
from rdc_auto.cli import build_parser, main


def test_package_exposes_version():
    import rdc_auto

    assert isinstance(rdc_auto.__version__, str)
    assert rdc_auto.__version__


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


def test_main_saves_expected_error_config_mutations(monkeypatch):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "s1"
    saved_executable_paths = []

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
            return Path("D:\\RenderDocMCP.exe")

    class FakeMcpClient:
        def __init__(self, executable_path):
            pass

        def ping(self):
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
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: saved_executable_paths.append(config.mcp.executable_path))
    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", FakeMcpClient)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["capture", "--out", "D:\\Captures"]) == 2
    assert saved_executable_paths == ["D:\\RenderDocMCP.exe"]


def test_attach_prepares_renderdoc_mcp_and_qrenderdoc_before_launch(monkeypatch):
    cfg = AppConfig.default()
    cfg.emulator.root_dir = "D:\\MuMu"
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
            return Path("D:\\RenderDocMCP.exe")

    class FakeMcpClient:
        def __init__(self, executable_path):
            self.executable_path = executable_path

        def ping(self):
            calls.append("ping")
            return True

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            self.config = config

        def attach(self, force=False, confirm_vulkan=False):
            calls.append("attach")
            return "s1"

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: calls.append("qrenderdoc"))
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", FakeMcpClient)
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["attach", "--yes-vulkan"]) == 0
    assert calls == ["renderdoc", "mcp", "qrenderdoc", "ping", "attach"]


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
        def __init__(self, executable_path):
            self.executable_path = executable_path

        def ping(self):
            return True

    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", NoSetupMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.FileIpcMcpClient", FakeMcpClient)
    monkeypatch.setattr("rdc_auto.cli._start_qrenderdoc", lambda config: None)

    assert Path(_mcp_client_for_test(monkeypatch, cfg).executable_path) == Path(cfg.mcp.executable_path)


def _mcp_client_for_test(monkeypatch, cfg):
    from rdc_auto.cli import _mcp_client

    return _mcp_client(cfg)


def test_start_qrenderdoc_reuses_existing_process(monkeypatch, tmp_path):
    from rdc_auto.cli import _start_qrenderdoc

    qrenderdoc = tmp_path / "qrenderdoc.exe"
    qrenderdoc.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(qrenderdoc)
    popen_calls = []

    def runner(args, capture_output, text, check):
        return type(
            "Result",
            (),
            {"stdout": '"Image Name","PID"\n"qrenderdoc.exe","1234"\n'},
        )()

    monkeypatch.setattr("rdc_auto.cli.subprocess.run", runner)
    monkeypatch.setattr("rdc_auto.cli.subprocess.Popen", lambda args, **kwargs: popen_calls.append(args))

    _start_qrenderdoc(cfg)

    assert popen_calls == []


def test_capture_prompts_to_attach_when_session_is_missing(monkeypatch, tmp_path):
    cfg = AppConfig.default()
    cfg.emulator.root_dir = "D:\\MuMu"
    output_dir = tmp_path / "captures"
    prompts = []

    class FakeCaptureService:
        def __init__(self, config, mcp, mumu):
            self.config = config

        def attach(self, force=False, confirm_vulkan=False):
            self.config.capture.active_session_id = "s1"
            return "s1"

        def capture(self, output_dir, timeout_seconds=60):
            return Path(output_dir) / "frame.rdc"

    def choose(label, options, default=None):
        prompts.append(label)
        return "attach" if "active" in label.lower() else "vulkan"

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli._mcp_client", lambda config: object())
    monkeypatch.setattr("rdc_auto.cli.choose_option", choose)
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["capture", "--out", str(output_dir)]) == 0
    assert any("active" in prompt.lower() for prompt in prompts)


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
    monkeypatch.setattr("rdc_auto.cli._mcp_client", lambda config: object())
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["capture", "--out", "D:\\Captures"]) == 1
    err = capsys.readouterr().err
    assert "missing dependency" in err
    assert "Unexpected error" not in err
