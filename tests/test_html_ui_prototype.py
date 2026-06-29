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
