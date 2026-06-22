from __future__ import annotations

import json
from pathlib import Path

from rdc_auto.config import AppConfig, config_path, load_config, save_config


def test_config_path_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    assert config_path() == tmp_path / "LocalAppData" / "RdcAutomation" / "config.json"


def test_load_config_returns_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    cfg = load_config()

    assert cfg.renderdoc.version == "1.44"
    assert cfg.mcp.release_api_url == "https://api.github.com/repos/Smilexs/RenderDocMCP/releases/latest"
    assert cfg.mcp.asset_name == ""
    assert cfg.mcp.executable_path == ""
    assert cfg.emulator.type == "mumu12"
    assert cfg.emulator.exe_relative_path == "MuMuPlayer-12.0\\nx_main\\MuMuNxMain.exe"
    assert cfg.emulator.graphics_api == "vulkan"


def test_save_and_reload_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    cfg = AppConfig.default()
    cfg.emulator.root_dir = "D:\\MuMu"
    cfg.capture.last_output_dir = "D:\\Captures"

    save_config(cfg)
    loaded = load_config()

    assert loaded.emulator.root_dir == "D:\\MuMu"
    assert loaded.capture.last_output_dir == "D:\\Captures"
    data = json.loads(config_path().read_text(encoding="utf-8"))
    assert data["emulator"]["graphics_api"] == "vulkan"


def test_default_config_has_gui_ai_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    cfg = load_config()

    assert cfg.gui.window_width == 1320
    assert cfg.gui.window_height == 860
    assert cfg.ai.provider == "openai"
    assert cfg.ai.model == "gpt-4.1-mini"
    assert cfg.ai.base_url == "https://api.openai.com/v1"
    assert cfg.ai.api_key == ""
    assert cfg.capture.active_launch_id == ""
