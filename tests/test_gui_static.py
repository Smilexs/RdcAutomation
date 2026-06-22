from __future__ import annotations

from pathlib import Path

from rdc_auto.gui.app import build_window_options
from rdc_auto.gui.paths import gui_static_dir, gui_index_path


def test_gui_index_is_packaged():
    index = gui_index_path()

    assert index == gui_static_dir() / "index.html"
    assert index.is_file()
    html = index.read_text(encoding="utf-8")
    assert "RdcAutomation" in html
    assert 'data-view-target="dashboard"' in html
    assert 'data-action="capture"' in html
    assert "window.pywebview" in html


def test_build_window_options_points_to_packaged_index():
    options = build_window_options()

    assert options["title"] == "RdcAutomation"
    assert options["url"].endswith("index.html")
    assert options["width"] == 1320
    assert options["height"] == 860
