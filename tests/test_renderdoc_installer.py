from __future__ import annotations

import subprocess

from rdc_auto.config import AppConfig
from rdc_auto.renderdoc_installer import RenderDocInstaller, parse_v144_windows_x64_url


def test_parse_v144_windows_x64_url_from_builds_html():
    html = """
    <a href="/stable/1.44/RenderDoc_1.44_64.msi">Windows 64-bit installer</a>
    <a href="/stable/1.43/RenderDoc_1.43_64.msi">Older installer</a>
    """

    assert parse_v144_windows_x64_url(html) == "https://renderdoc.org/stable/1.44/RenderDoc_1.44_64.msi"


def test_parse_v144_windows_x64_url_accepts_absolute_url():
    html = '<a href="https://renderdoc.org/stable/1.44/RenderDoc_1.44_64.exe">Windows 64-bit installer</a>'

    assert parse_v144_windows_x64_url(html) == "https://renderdoc.org/stable/1.44/RenderDoc_1.44_64.exe"


def test_installer_updates_config_when_existing_renderdoc_found(tmp_path):
    qrenderdoc = tmp_path / "RenderDoc" / "qrenderdoc.exe"
    renderdoccmd = tmp_path / "RenderDoc" / "renderdoccmd.exe"
    qrenderdoc.parent.mkdir()
    qrenderdoc.write_text("", encoding="utf-8")
    renderdoccmd.write_text("", encoding="utf-8")
    cfg = AppConfig.default()

    installer = RenderDocInstaller(
        config=cfg,
        finder=lambda: {
            "install_dir": str(qrenderdoc.parent),
            "qrenderdoc_path": str(qrenderdoc),
            "renderdoccmd_path": str(renderdoccmd),
        },
    )

    assert installer.ensure_installed() is True
    assert cfg.renderdoc.qrenderdoc_path == str(qrenderdoc)
    assert cfg.renderdoc.renderdoccmd_path == str(renderdoccmd)


def test_run_installer_uses_default_options(tmp_path):
    installer_file = tmp_path / "RenderDoc_1.44_64.msi"
    installer_file.write_text("", encoding="utf-8")
    calls = []

    def runner(args, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    installer = RenderDocInstaller(config=AppConfig.default(), runner=runner)
    installer.run_installer(installer_file)

    assert calls == [["msiexec", "/i", str(installer_file), "/passive"]]
