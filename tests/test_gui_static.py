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


def test_gui_index_has_backend_action_mapping():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "function callBackend" in html
    assert "function runJobAction" in html
    assert '"check-env": "check_environment"' in html
    assert '"attach": "attach"' in html
    assert '"capture": "capture"' in html
    assert '"export": "export"' in html
    assert 'window.RdcBackend.call("start_job"' in html


def test_gui_index_deduplicates_backend_job_logs():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'callBackend("get_job", { job_id: jobId }, { replayLogs: false })' in html
    assert "let lastLogIndex = 0" in html


def test_gui_index_preserves_non_empty_form_values_on_status_hydration():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "function setValueIfPresent" in html
    assert 'value !== ""' in html


def test_gui_index_routes_mcp_actions_to_mcp_progress():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'id="mcpProgress"' in html
    assert 'return "#mcpProgress"' in html


def test_gui_index_routes_choose_actions_to_backend_dialogs():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'action === "choose-mumu"' in html
    assert 'callBackend("choose_directory"' in html
    assert 'action === "choose-rdc"' in html
    assert 'callBackend("choose_file"' in html
    assert "function applyDialogValue" in html
    assert "state.backendConfigPreview = null" in html
    assert "state.lastRdcPath = response.data.path" in html


def test_gui_index_routes_eid_actions_to_backend():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'callBackend("load_eid_list"' in html
    assert 'callBackend("export_eid_model"' in html
    assert 'callBackend("export_eid_textures"' in html


def test_gui_index_routes_eid_row_actions_to_backend_exports():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'rowAction.dataset.rowAction === "model" ? "export-eid-model" : "export-eid-textures"' in html
    assert "return handleAction(action);" in html


def test_gui_index_escapes_backend_text_in_eid_table_and_toasts():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "function escapeHtml" in html
    assert "escapeHtml(title)" in html
    assert "escapeHtml(body)" in html
    assert "${escapeHtml(row.name)}" in html
    assert "${escapeHtml(row.mesh)}" in html
    assert "${escapeHtml(row.textures)}" in html


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
