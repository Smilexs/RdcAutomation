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


def test_gui_index_keeps_sidebar_fixed_while_main_content_scrolls():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "body {" in html
    assert "overflow: hidden;" in html[html.index("body {") : html.index("button,", html.index("body {"))]
    assert "height: 100vh;" in html[html.index(".app {") : html.index(".sidebar {")]
    assert "position: sticky;" in html[html.index(".sidebar {") : html.index(".brand {")]
    assert "overflow-y: auto;" in html[html.index(".main {") : html.index(".topbar {")]
    assert "@media (max-width: 760px)" in html
    mobile = html[html.index("@media (max-width: 760px)") :]
    assert "overflow: auto;" in mobile


def test_gui_index_uses_distinct_capture_and_export_output_defaults():
    html = gui_index_path().read_text(encoding="utf-8")

    assert '<input id="captureOut" value="D:\\RdcCaptures" />' in html
    assert '<input id="exportOut" value="D:\\RdcExports" />' in html
    assert "paths.capture_output_dir" in html
    assert "paths.export_output_dir" in html
    assert "capture_output_dir: $(\"#captureOut\")?.value || \"\"" in html
    assert "export_output_dir: $(\"#exportOut\")?.value || \"\"" in html


def test_gui_index_has_backend_action_mapping():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "function callBackend" in html
    assert "function runJobAction" in html
    assert '"check-env": "check_environment"' in html
    assert '"install-env": "setup_renderdoc"' in html
    assert '"install-mcp": "setup_mcp"' in html
    assert '"auto-install-tools": "setup_renderdoc_mcp"' in html
    assert '"attach": "attach"' in html
    assert '"capture": "capture"' in html
    assert '"export": "export"' in html
    assert 'window.RdcBackend.call("start_job"' in html


def test_renderdoc_environment_actions_save_path_and_show_logged_prominent_errors():
    html = gui_index_path().read_text(encoding="utf-8")
    renderdoc_view = html[html.index('id="view-environment"') : html.index('data-section="ai-config"')]

    assert 'data-action="open-settings"' not in renderdoc_view
    assert 'callBackend("save_environment", collectEnvironmentParams())' in html
    assert "function jobFailureTitle" in html
    assert 'toast(title, message, "danger")' in html
    assert "提示：" in html


def test_renderdoc_card_contains_mcp_path_and_only_requested_buttons():
    html = gui_index_path().read_text(encoding="utf-8")
    environment_view = html[html.index('id="view-environment"') : html.index('data-section="ai-config"')]
    renderdoc_card = environment_view[: environment_view.index("MuMu12")]

    assert 'data-section="mcp-config"' not in environment_view
    assert 'id="renderdocPath"' in renderdoc_card
    assert 'id="mcpPath"' in renderdoc_card
    assert renderdoc_card.index('id="renderdocPath"') < renderdoc_card.index('id="mcpPath"')
    assert '<input id="renderdocPath" value="" />' in renderdoc_card
    assert '<input id="mcpPath" value="" />' in renderdoc_card
    assert 'id="renderdocPathWarning"' in renderdoc_card
    assert 'id="mcpPathWarning"' in renderdoc_card
    assert 'data-action="check-env"' in renderdoc_card
    assert 'data-action="install-env"' in renderdoc_card
    assert 'data-action="install-mcp"' in renderdoc_card
    assert 'data-action="save-mcp"' not in environment_view
    assert 'data-action="open-mcp-dir"' not in environment_view


def test_check_environment_prompts_auto_install_when_tools_missing():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "function shouldPromptAutoInstall" in html
    assert "function confirmAutoInstallTools" in html
    assert 'state.pendingConfirmAction = "auto-install-tools"' in html
    assert 'handleAction("auto-install-tools")' in html


def test_path_warnings_update_from_backend_status_and_input():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "renderdocInvalidReason" in html
    assert "mcpInvalidReason" in html
    assert "function updateToolPathWarnings" in html
    assert "renderdoc.invalid_reason" in html
    assert "mcp.invalid_reason" in html
    assert 'if (id === "renderdocPath" || id === "mcpPath") node.addEventListener("input", handleToolPathInput);' in html


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


def test_gui_index_check_mcp_refreshes_status_without_starting_mcp():
    html = gui_index_path().read_text(encoding="utf-8")

    assert '"check-mcp": "start_mcp"' not in html
    assert 'action === "refresh-status" || action === "check-mcp"' in html


def test_gui_index_initial_mcp_state_is_not_hardcoded_running():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "mcpReady: false" in html
    assert "mcpRunning: false" in html
    assert "mcpExtensionLoaded: false" in html
    assert "mcpRunning: true" not in html


def test_gui_index_routes_choose_actions_to_backend_dialogs():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'action === "choose-mumu"' in html
    assert 'callBackend("choose_directory"' in html
    assert 'action === "choose-rdc"' in html
    assert 'callBackend("choose_file"' in html
    assert "function applyDialogValue" in html
    assert "state.backendConfigPreview = null" in html
    assert 'applyRdcSelection(response.data.path, { updateLastRdc: true })' in html


def test_gui_index_routes_eid_actions_to_backend():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'callBackend("load_eid_list"' in html
    assert 'callBackend("export_eid_model"' in html
    assert 'callBackend("export_eid_textures"' in html


def test_gui_index_routes_eid_row_actions_to_backend_exports():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'rowAction.dataset.rowAction === "model" ? "export-eid-model" : "export-eid-textures"' in html
    assert "return handleAction(action);" in html


def test_environment_cards_are_vertical_and_include_ai_config_after_mcp():
    html = gui_index_path().read_text(encoding="utf-8")
    environment_view = html[html.index('id="view-environment"') : html.index('id="view-capture"')]

    assert '<div class="grid environment-stack">' in environment_view
    assert '<div class="grid two">' not in environment_view
    assert environment_view.index('id="mcpPath"') < environment_view.index('data-section="ai-config"')
    assert "功能开发中" in environment_view


def test_ai_config_is_removed_from_assistant_view():
    html = gui_index_path().read_text(encoding="utf-8")
    assistant_view = html[html.index('id="view-assistant"') : html.index('id="view-logs"')]

    assert 'data-section="ai-config"' not in assistant_view
    assert 'id="aiProvider"' not in assistant_view


def test_logs_view_stacks_config_summary_above_log_panel_and_removes_prototype_actions():
    html = gui_index_path().read_text(encoding="utf-8")
    logs_view = html[html.index('id="view-logs"') : html.index('<div class="toast-root"', html.index('id="view-logs"'))]

    assert '<div class="logs-stack">' in logs_view
    assert logs_view.index('id="configPreview"') < logs_view.index('class="log-panel"')
    assert 'aria-label="日志"' in logs_view
    assert 'data-action="copy-config"' not in logs_view
    assert 'data-action="reset-prototype"' not in logs_view
    assert 'data-action="show-danger"' not in logs_view
    assert "原型操作" not in logs_view


def test_mumu_root_defaults_empty_and_has_warning_ui():
    html = gui_index_path().read_text(encoding="utf-8")

    assert '<input id="mumuRoot" value="" />' in html
    assert 'id="mumuPathWarning"' in html
    assert "请选择直接包含 nx_main 的目录作为 MuMu12 根目录" in html
    assert "D:\\Softwares\\MuMuPlayer" in html
    assert "保存后会自动规范为其父目录" in html
    assert "MuMuPlayer-12.0" not in html
    assert "MuMuNxMain.exe 完整路径" not in html
    assert "function updateMumuPathWarning" in html
    assert "mumu.invalid_reason" in html


def test_mumu_root_input_clears_stale_unconfigured_warning():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "function handleMumuRootInput" in html
    assert "state.mumuReady = Boolean(root);" in html
    assert "updateStatus();" in html[html.index("function handleMumuRootInput") : html.index("function updateMcpCards")]
    assert 'if (id === "mumuRoot") node.addEventListener("input", handleMumuRootInput);' in html
    assert 'message = message || "MuMu12 路径无效' not in html


def test_export_panel_uses_current_backend_copy_and_asset_options():
    html = gui_index_path().read_text(encoding="utf-8")
    export_view = html[html.index('id="view-export"') : html.index('id="view-assistant"')]

    assert "普通导出使用本地后端从 RDC 导出资源，高级 EID 支持按绘制事件导出模型或绑定贴图。" in export_view
    assert '<option value="textures">所有贴图</option>' in export_view
    assert '<option value="meshes">所有模型</option>' in export_view
    assert '<option value="both">' not in export_view
    assert "前端模拟" not in export_view


def test_export_rdc_and_eid_defaults_are_empty_until_recent_capture():
    html = gui_index_path().read_text(encoding="utf-8")
    export_view = html[html.index('id="view-export"') : html.index('id="view-assistant"')]

    assert '<input id="rdcPath" value="" />' in export_view
    assert '<input id="eidInput" value="" />' in export_view
    assert '<input id="eidRdcPath" value="" />' in export_view
    assert 'lastRdcPath: "",' in html
    assert "let eidRows = [];" in html
    assert "mumu12_20260617_160827.rdc" not in export_view


def test_export_rdc_selection_is_persisted_through_backend():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'async function persistCapturePaths()' in html
    assert 'callBackend("save_capture_paths"' in html
    assert 'node.addEventListener("change", persistCapturePaths)' in html


def test_export_open_directory_routes_to_backend_open_path():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'action === "open-export-out"' in html
    assert 'callBackend("open_path", { path: $("#exportOut")?.value || "" })' in html
    assert 'action === "open-mcp-dir"' in html
    assert "parentDirectory($(\"#mcpPath\")?.value || \"\")" in html


def test_eid_table_is_scrollable_and_filters_assetless_rows():
    html = gui_index_path().read_text(encoding="utf-8")

    assert 'class="table-wrap eid-table-wrap"' in html
    assert ".eid-table-wrap" in html
    assert "max-height: 360px" in html
    assert "function rowHasExportableAsset" in html
    assert "rows.map(normalizeEidRow).filter(rowHasExportableAsset)" in html


def test_dashboard_copy_and_quick_flow_are_navigation_first():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "按顺序完成检查、连接、捕捉和导出。" in html
    assert "面向普通用户的一键式操作入口。" not in html
    assert 'data-action="quick-attach"' not in html
    assert 'data-action="quick-capture"' not in html
    assert 'data-view-target="capture"' in html


def test_dashboard_recent_rdc_replaces_task_summary():
    html = gui_index_path().read_text(encoding="utf-8")

    assert "任务结果" not in html
    assert 'id="summaryList"' not in html
    assert 'id="recentRdcList"' in html
    assert 'callBackend("list_rdc_files"' in html
    assert 'data-use-rdc="${escapeHtml(path)}"' in html


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
            self.shutdown_called = False
            bridges.append(self)

        def bind_window(self, bound_window):
            self.bound_window = bound_window

        def shutdown(self, payload=None):
            self.shutdown_called = True

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
    assert bridges[0].shutdown_called is True
