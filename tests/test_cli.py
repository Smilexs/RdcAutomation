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

        def ensure_installed(self):
            return Path("D:\\RenderDocMCP.exe")

    monkeypatch.setattr("rdc_auto.cli.configure_logging", lambda verbose=False: None)
    monkeypatch.setattr("rdc_auto.cli.load_config", lambda: cfg)
    monkeypatch.setattr("rdc_auto.cli.save_config", lambda config: None)
    monkeypatch.setattr("rdc_auto.cli.RenderDocInstaller", FakeRenderDocInstaller)
    monkeypatch.setattr("rdc_auto.cli.find_renderdoc_install", lambda: {"install_dir": "", "qrenderdoc_path": "", "renderdoccmd_path": ""})
    monkeypatch.setattr("rdc_auto.cli.validate_mumu_root", lambda root: Path("D:\\MuMu\\MuMuPlayer-12.0\\nx_main\\MuMuNxMain.exe"))
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)

    assert main(["setup"]) == 1
    assert "setup complete" not in capsys.readouterr().out


def test_main_saves_expected_error_config_mutations(monkeypatch):
    cfg = AppConfig.default()
    saved_executable_paths = []

    class FakeMcpInstaller:
        def __init__(self, config):
            self.config = config

        def ensure_installed(self):
            return Path("D:\\RenderDocMCP.exe")

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
    monkeypatch.setattr("rdc_auto.cli.McpInstaller", FakeMcpInstaller)
    monkeypatch.setattr("rdc_auto.cli.CaptureService", FakeCaptureService)

    assert main(["capture", "--out", "D:\\Captures"]) == 2
    assert saved_executable_paths == ["D:\\RenderDocMCP.exe"]
