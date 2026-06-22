from __future__ import annotations

from pathlib import Path

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
