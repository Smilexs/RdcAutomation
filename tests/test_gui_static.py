from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from rdc_auto.config import AppConfig
from rdc_auto.gui import app as gui_app
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


def test_build_window_options_points_to_packaged_index(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    options = gui_app.build_window_options()

    assert options["title"] == "RdcAutomation"
    assert options["url"].endswith("index.html")
    assert options["width"] == 1320
    assert options["height"] == 860
    assert options["min_size"] == (1100, 720)


def test_main_creates_window_with_bridge_and_starts_debug(monkeypatch):
    cfg = AppConfig.default()
    cfg.gui.window_width = 1440
    cfg.gui.window_height = 900
    window = object()
    created = {}
    started = {}
    bridges = []

    class FakeBridge:
        def __init__(self):
            self.bound_window = None
            bridges.append(self)

        def bind_window(self, bound_window):
            self.bound_window = bound_window

    def create_window(title, url, **kwargs):
        created.update({"title": title, "url": url, **kwargs})
        return window

    def start(**kwargs):
        started.update(kwargs)

    fake_webview = SimpleNamespace(create_window=create_window, start=start)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setattr(gui_app, "GuiBridge", FakeBridge)
    monkeypatch.setattr(gui_app, "load_config", lambda: cfg)

    result = gui_app.main(debug=True)

    assert result == 0
    assert created["title"] == "RdcAutomation"
    assert created["url"].endswith("index.html")
    assert created["js_api"] is bridges[0]
    assert created["width"] == 1440
    assert created["height"] == 900
    assert created["min_size"] == (1100, 720)
    assert bridges[0].bound_window is window
    assert started == {"debug": True}
