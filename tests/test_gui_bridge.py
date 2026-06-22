from __future__ import annotations

from rdc_auto.config import AppConfig
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
