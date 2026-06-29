from __future__ import annotations

import subprocess

import pytest

from rdc_auto.config import AppConfig
from rdc_auto.mcp_installer import McpInstaller, parse_release_asset


def test_parse_release_asset_picks_setup_exe():
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {"name": "source.zip", "browser_download_url": "https://example/source.zip"},
            {
                "name": "RenderDocMCP-Setup-1.0.0.exe",
                "browser_download_url": "https://example/RenderDocMCP-Setup-1.0.0.exe",
                "digest": "sha256:abc123",
            },
        ],
    }

    asset = parse_release_asset(release)

    assert asset.name == "RenderDocMCP-Setup-1.0.0.exe"
    assert asset.download_url == "https://example/RenderDocMCP-Setup-1.0.0.exe"
    assert asset.digest == "sha256:abc123"


def test_parse_release_asset_ignores_other_setup_exes():
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {
                "name": "OtherTool-Setup-1.0.0.exe",
                "browser_download_url": "https://example/OtherTool-Setup-1.0.0.exe",
            },
            {
                "name": "RenderDocMCP-Setup-1.0.0.exe",
                "browser_download_url": "https://example/RenderDocMCP-Setup-1.0.0.exe",
            },
        ],
    }

    asset = parse_release_asset(release)

    assert asset.name == "RenderDocMCP-Setup-1.0.0.exe"
    assert asset.download_url == "https://example/RenderDocMCP-Setup-1.0.0.exe"


def test_parse_release_asset_rejects_other_setup_exes():
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {
                "name": "OtherTool-Setup-1.0.0.exe",
                "browser_download_url": "https://example/OtherTool-Setup-1.0.0.exe",
            },
        ],
    }

    with pytest.raises(ValueError):
        parse_release_asset(release)


def test_download_latest_installer_does_not_record_release_asset_before_install(tmp_path):
    cfg = AppConfig.default()
    cfg.mcp.install_dir = str(tmp_path / "mcp")
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {
                "name": "RenderDocMCP-Setup-1.0.0.exe",
                "browser_download_url": "https://example/RenderDocMCP-Setup-1.0.0.exe",
                "digest": "sha256:abc123",
            }
        ],
    }

    def fetch_json(url):
        assert url == cfg.mcp.release_api_url
        return release

    def downloader(url, target):
        assert url == "https://example/RenderDocMCP-Setup-1.0.0.exe"
        target.write_bytes(b"exe")

    installer = McpInstaller(cfg, fetch_json=fetch_json, downloader=downloader)
    path = installer.download_latest_installer()

    assert path == tmp_path / "mcp" / "downloads" / "RenderDocMCP-Setup-1.0.0.exe"
    assert cfg.mcp.asset_name == ""
    assert cfg.mcp.asset_digest == ""
    assert cfg.mcp.installer_path == ""


def test_run_installer_executes_downloaded_exe(tmp_path):
    setup = tmp_path / "RenderDocMCP-Setup-1.0.0.exe"
    setup.write_bytes(b"exe")
    calls = []
    cfg = AppConfig.default()

    def runner(args, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    installer = McpInstaller(cfg, runner=runner)
    installer.run_installer(setup)

    assert calls == [[str(setup)]]


def test_discover_executable_prefers_configured_path(tmp_path):
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.mcp.executable_path = str(exe)

    installer = McpInstaller(cfg)

    assert installer.discover_executable() == exe


def test_discover_executable_checks_localappdata_renderdocmcp(tmp_path, monkeypatch):
    local_app_data = tmp_path / "LocalAppData"
    exe = local_app_data / "RenderDocMCP" / "RenderDocMCP.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"exe")
    cfg = AppConfig.default()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    installer = McpInstaller(cfg)

    assert installer.discover_executable() == exe
    assert cfg.mcp.executable_path == str(exe)


def test_ensure_installed_reinstalls_stale_configured_exe_from_latest_release(tmp_path):
    old_exe = tmp_path / "old" / "RenderDocMCP.exe"
    old_exe.parent.mkdir()
    old_exe.write_bytes(b"old")
    cfg = AppConfig.default()
    cfg.mcp.install_dir = str(tmp_path / "mcp")
    cfg.mcp.executable_path = str(old_exe)
    cfg.mcp.asset_name = "RenderDocMCP-Setup-0.9.0.exe"
    cfg.mcp.asset_digest = "sha256:old"
    release = {
        "assets": [
            {
                "name": "RenderDocMCP-Setup-1.0.0.exe",
                "browser_download_url": "https://example/RenderDocMCP-Setup-1.0.0.exe",
                "digest": "sha256:new",
            }
        ]
    }
    calls = []

    def downloader(url, target):
        calls.append(("download", url, target.name))
        target.write_bytes(b"setup")

    def runner(args, check):
        calls.append(("run", args[0]))
        installed = tmp_path / "mcp" / "RenderDocMCP.exe"
        installed.write_bytes(b"new")
        return subprocess.CompletedProcess(args, 0)

    installer = McpInstaller(cfg, fetch_json=lambda url: release, downloader=downloader, runner=runner)

    assert installer.ensure_installed() == tmp_path / "mcp" / "RenderDocMCP.exe"
    assert cfg.mcp.asset_name == "RenderDocMCP-Setup-1.0.0.exe"
    assert cfg.mcp.asset_digest == "sha256:new"
    assert cfg.mcp.executable_path == str(tmp_path / "mcp" / "RenderDocMCP.exe")
    assert calls == [
        ("download", "https://example/RenderDocMCP-Setup-1.0.0.exe", "RenderDocMCP-Setup-1.0.0.exe"),
        ("run", str(tmp_path / "mcp" / "downloads" / "RenderDocMCP-Setup-1.0.0.exe")),
    ]


def test_ensure_installed_does_not_record_latest_release_when_installer_fails(tmp_path):
    old_exe = tmp_path / "old" / "RenderDocMCP.exe"
    old_exe.parent.mkdir()
    old_exe.write_bytes(b"old")
    cfg = AppConfig.default()
    cfg.mcp.install_dir = str(tmp_path / "mcp")
    cfg.mcp.executable_path = str(old_exe)
    cfg.mcp.asset_name = "RenderDocMCP-Setup-0.9.0.exe"
    cfg.mcp.asset_digest = "sha256:old"
    cfg.mcp.release_tag = "v0.9.0"
    cfg.mcp.installer_path = str(tmp_path / "old-setup.exe")
    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {
                "name": "RenderDocMCP-Setup-1.0.0.exe",
                "browser_download_url": "https://example/RenderDocMCP-Setup-1.0.0.exe",
                "digest": "sha256:new",
            }
        ],
    }

    def downloader(url, target):
        target.write_bytes(b"setup")

    def runner(args, check):
        raise subprocess.CalledProcessError(1, args)

    installer = McpInstaller(cfg, fetch_json=lambda url: release, downloader=downloader, runner=runner)

    with pytest.raises(subprocess.CalledProcessError):
        installer.ensure_installed()

    assert cfg.mcp.asset_name == "RenderDocMCP-Setup-0.9.0.exe"
    assert cfg.mcp.asset_digest == "sha256:old"
    assert cfg.mcp.release_tag == "v0.9.0"
    assert cfg.mcp.installer_path == str(tmp_path / "old-setup.exe")
    assert cfg.mcp.executable_path == str(old_exe)


def test_ensure_installed_accepts_configured_exe_only_when_release_asset_matches(tmp_path):
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.mcp.executable_path = str(exe)
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"
    cfg.mcp.asset_digest = "sha256:abc123"
    release = {
        "assets": [
            {
                "name": "RenderDocMCP-Setup-1.0.0.exe",
                "browser_download_url": "https://example/RenderDocMCP-Setup-1.0.0.exe",
                "digest": "sha256:abc123",
            }
        ]
    }

    def downloader(url, target):
        raise AssertionError("current release should not be downloaded")

    def runner(args, check):
        raise AssertionError("current release should not be installed")

    installer = McpInstaller(cfg, fetch_json=lambda url: release, downloader=downloader, runner=runner)

    assert installer.ensure_installed() == exe


def test_runtime_executable_uses_recorded_release_install_without_fetching_latest(tmp_path):
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.0.exe"
    cfg.mcp.executable_path = str(exe)

    installer = McpInstaller(
        cfg,
        fetch_json=lambda url: (_ for _ in ()).throw(AssertionError("runtime path must not query GitHub")),
        downloader=lambda url, target: (_ for _ in ()).throw(AssertionError("runtime path must not download")),
        runner=lambda args, check: (_ for _ in ()).throw(AssertionError("runtime path must not run installer")),
    )

    assert installer.runtime_executable() == exe


def test_runtime_executable_accepts_existing_exe_without_release_setup_record(tmp_path):
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    cfg = AppConfig.default()
    cfg.mcp.executable_path = str(exe)

    installer = McpInstaller(
        cfg,
        fetch_json=lambda url: (_ for _ in ()).throw(AssertionError("runtime path must not query GitHub")),
        downloader=lambda url, target: (_ for _ in ()).throw(AssertionError("runtime path must not download")),
        runner=lambda args, check: (_ for _ in ()).throw(AssertionError("runtime path must not run installer")),
    )

    assert installer.runtime_executable() == exe
