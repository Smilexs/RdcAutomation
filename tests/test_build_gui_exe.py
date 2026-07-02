from __future__ import annotations

from pathlib import Path


def test_gui_exe_build_bundles_mcp_source_without_setup_installer():
    script = Path("scripts/build_gui_exe.ps1").read_text(encoding="utf-8")

    assert "renderdoc_mcp" in script
    assert "--noupx" in script
    assert "installers" not in script
    assert "RenderDocMCP-Setup" not in script
