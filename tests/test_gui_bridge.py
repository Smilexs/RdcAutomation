from __future__ import annotations

from rdc_auto.config import AppConfig
from rdc_auto.gui.bridge import GuiBridge
from rdc_auto.gui.status import build_status_snapshot


def test_build_status_snapshot_contains_topbar_sections(tmp_path):
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(tmp_path / "qrenderdoc.exe")
    cfg.mcp.executable_path = str(tmp_path / "RenderDocMCP.exe")
    cfg.emulator.root_dir = str(tmp_path / "MuMu")
    cfg.capture.active_launch_id = "launch-1"

    snapshot = build_status_snapshot(cfg, process_counts={"qrenderdoc.exe": 1})

    assert snapshot["renderdoc"]["path"].endswith("qrenderdoc.exe")
    assert snapshot["mcp"]["running"] is True
    assert snapshot["session"]["attached"] is True
    assert snapshot["session"]["launch_id"] == "launch-1"
    assert snapshot["config_preview"]["capture"]["active_launch_id"] == "launch-1"


def test_build_status_snapshot_empty_process_counts_are_authoritative(monkeypatch):
    cfg = AppConfig.default()

    def fail_count_processes(name: str) -> int:
        raise AssertionError(f"unexpected live process probe for {name}")

    monkeypatch.setattr("rdc_auto.gui.status.count_processes", fail_count_processes)

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["mcp"]["running"] is False
    assert snapshot["mcp"]["extension_loaded"] is False


def test_build_status_snapshot_masks_saved_ai_api_key():
    cfg = AppConfig.default()
    cfg.ai.api_key = "sk-secret"

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["ai"]["api_key_saved"] is True
    assert snapshot["config_preview"]["ai"]["api_key"] == "********"


def test_bridge_get_status_returns_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.get_status({})

    assert response["ok"] is True
    assert "renderdoc" in response["data"]
    assert response["logs"] == []


def test_bridge_save_environment_updates_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_environment(
        {
            "renderdoc_path": "C:\\Program Files\\RenderDoc\\qrenderdoc.exe",
            "mumu_root": "D:\\MuMu",
            "vm_index": "1",
            "graphics_api": "vulkan",
        }
    )

    assert response["ok"] is True
    assert response["data"]["mumu"]["vm_index"] == "1"
