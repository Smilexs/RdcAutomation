from __future__ import annotations

import json
from pathlib import Path

import pytest

from rdc_auto.config import AppConfig
from rdc_auto.errors import DependencyMissing
from rdc_auto.mcp_installer import McpInstaller


def test_ensure_installed_syncs_embedded_source_and_installs_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    cfg = AppConfig.default()
    cfg.mcp.install_dir = str(tmp_path / "mcp")
    source = _write_source_tree(tmp_path / "embedded" / "renderdoc_mcp")

    installer = McpInstaller(
        cfg,
        fetch_json=lambda url: (_ for _ in ()).throw(AssertionError("GitHub must not be queried")),
        downloader=lambda url, target: (_ for _ in ()).throw(AssertionError("installer must not be downloaded")),
        runner=lambda args, check: (_ for _ in ()).throw(AssertionError("setup exe must not be run")),
        source_roots=[source],
    )

    extension_dir = installer.ensure_installed()

    installed_source = Path(cfg.mcp.install_dir) / "renderdoc_mcp"
    assert extension_dir == tmp_path / "Roaming" / "qrenderdoc" / "extensions" / "renderdoc_mcp_bridge"
    assert (extension_dir / "extension.json").read_text(encoding="utf-8") == '{"name":"test"}'
    assert (installed_source / "mcp_server" / "server.py").read_text(encoding="utf-8") == "def main():\n    pass\n"
    assert not (installed_source / "mcp_server" / "__pycache__").exists()
    assert cfg.mcp.source_path == str(installed_source)
    assert cfg.mcp.extension_dir == str(extension_dir)
    assert cfg.mcp.executable_path == ""
    assert cfg.mcp.asset_name == "RenderDocMCP source"
    assert cfg.mcp.release_tag == "v9.8.7"

    ui_config = json.loads((tmp_path / "Roaming" / "qrenderdoc" / "UI.config").read_text(encoding="utf-8"))
    assert "renderdoc_mcp_bridge" in ui_config["AlwaysLoad_Extensions"]


def test_runtime_extension_dir_uses_recorded_extension_without_source_lookup(tmp_path):
    cfg = AppConfig.default()
    extension_dir = tmp_path / "extensions" / "renderdoc_mcp_bridge"
    extension_dir.mkdir(parents=True)
    (extension_dir / "extension.json").write_text("{}", encoding="utf-8")
    cfg.mcp.extension_dir = str(extension_dir)

    installer = McpInstaller(
        cfg,
        fetch_json=lambda url: (_ for _ in ()).throw(AssertionError("runtime must not query GitHub")),
        downloader=lambda url, target: (_ for _ in ()).throw(AssertionError("runtime must not download")),
        runner=lambda args, check: (_ for _ in ()).throw(AssertionError("runtime must not run installer")),
        source_roots=[tmp_path / "missing"],
    )

    assert installer.runtime_extension_dir() == extension_dir


def test_runtime_extension_dir_requires_setup_when_extension_is_missing(tmp_path):
    cfg = AppConfig.default()
    cfg.mcp.extension_dir = str(tmp_path / "missing" / "renderdoc_mcp_bridge")

    with pytest.raises(DependencyMissing, match="RenderDocMCP extension was not found"):
        McpInstaller(cfg, source_roots=[tmp_path / "missing-source"]).runtime_extension_dir()


def test_ensure_installed_accepts_source_already_in_install_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    cfg = AppConfig.default()
    cfg.mcp.install_dir = str(tmp_path / "mcp")
    source = _write_source_tree(Path(cfg.mcp.install_dir) / "renderdoc_mcp")

    extension_dir = McpInstaller(cfg, source_roots=[source]).ensure_installed()

    assert extension_dir.exists()
    assert (source / "mcp_server" / "server.py").is_file()


def test_discover_extension_accepts_legacy_executable_parent_extension(tmp_path):
    cfg = AppConfig.default()
    exe = tmp_path / "RenderDocMCP.exe"
    extension_dir = tmp_path / "renderdoc_extension"
    exe.write_bytes(b"exe")
    extension_dir.mkdir()
    (extension_dir / "extension.json").write_text("{}", encoding="utf-8")
    cfg.mcp.executable_path = str(exe)

    found = McpInstaller(cfg).discover_extension()

    assert found == extension_dir
    assert cfg.mcp.extension_dir == str(extension_dir)


def _write_source_tree(root: Path) -> Path:
    (root / "renderdoc_extension").mkdir(parents=True)
    (root / "renderdoc_extension" / "extension.json").write_text('{"name":"test"}', encoding="utf-8")
    (root / "renderdoc_extension" / "__init__.py").write_text("", encoding="utf-8")
    (root / "mcp_server").mkdir()
    (root / "mcp_server" / "__init__.py").write_text("", encoding="utf-8")
    (root / "mcp_server" / "server.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (root / "mcp_server" / "__pycache__").mkdir()
    (root / "mcp_server" / "__pycache__" / "server.pyc").write_bytes(b"pyc")
    (root / "pyproject.toml").write_text('[project]\nname = "renderdoc-mcp"\nversion = "9.8.7"\n', encoding="utf-8")
    return root
