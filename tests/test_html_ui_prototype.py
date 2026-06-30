from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "html-ui-prototype" / "index.html"


def _environment_mcp_panel() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    view_start = html.index('<section class="view" id="view-environment">')
    view_end = html.index('<section class="view" id="view-capture">', view_start)
    environment_view = html[view_start:view_end]
    title_pos = environment_view.index("<h3 class=\"panel-title\">RenderDoc MCP</h3>")
    panel_start = environment_view.rfind('<section class="panel">', 0, title_pos)
    panel_end = environment_view.index("\n          </section>", title_pos)
    return environment_view[panel_start:panel_end]


def _logs_view() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    view_start = html.index('<section class="view" id="view-logs">')
    view_end = html.index('<div class="toast-root"', view_start)
    return html[view_start:view_end]


def test_environment_renderdoc_mcp_panel_only_shows_path_and_settings_buttons():
    panel = _environment_mcp_panel()

    assert 'id="mcpPath"' in panel
    assert 'data-action="save-mcp"' in panel
    assert 'data-action="install-mcp"' in panel
    assert 'data-action="open-mcp-dir"' in panel

    removed_controls = [
        'data-action="check-mcp"',
        'data-action="start-mcp"',
        'data-action="stop-mcp"',
        'data-action="restart-mcp"',
        'data-action="open-mcp-release"',
        'id="mcpPageStatus"',
        'id="mcpVersionText"',
        'id="mcpExtensionText"',
        'id="mcpReleaseTag"',
        'id="mcpMode"',
        'id="mcpProgress"',
    ]
    for control in removed_controls:
        assert control not in panel


def test_logs_view_stacks_config_summary_above_log_panel_and_removes_prototype_actions():
    logs_view = _logs_view()

    assert '<div class="logs-stack">' in logs_view
    assert logs_view.index('id="configPreview"') < logs_view.index('class="log-panel"')
    assert 'aria-label="日志"' in logs_view
    assert 'data-action="copy-config"' not in logs_view
    assert 'data-action="reset-prototype"' not in logs_view
    assert 'data-action="show-danger"' not in logs_view
    assert "原型操作" not in logs_view


def test_export_panel_uses_current_copy_asset_options_and_scrollable_eid_table():
    html = INDEX_HTML.read_text(encoding="utf-8")
    export_view = html[html.index('id="view-export"') : html.index('id="view-assistant"')]

    assert "普通导出生成贴图或模型，高级 EID 可按绘制事件导出模型或绑定贴图。" in export_view
    assert '<option value="textures">所有贴图</option>' in export_view
    assert '<option value="meshes">所有模型</option>' in export_view
    assert '<option value="both">' not in export_view
    assert 'class="table-wrap eid-table-wrap"' in export_view
    assert "前端模拟" not in export_view
    assert ".eid-table-wrap" in html
