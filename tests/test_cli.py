from __future__ import annotations

from pathlib import Path

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
