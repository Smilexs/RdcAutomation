from __future__ import annotations

import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable

from .config import AppConfig, app_data_dir
from .paths import find_renderdoc_install


BUILDS_URL = "https://renderdoc.org/builds"
RENDERDOC_VERSION = "1.44"


def parse_v144_windows_x64_url(html: str) -> str:
    hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    for href in hrefs:
        lower = href.lower()
        if "1.44" in lower and ("_64" in lower or "x64" in lower) and (lower.endswith(".msi") or lower.endswith(".exe")):
            if href.startswith("http://") or href.startswith("https://"):
                return href
            if href.startswith("/"):
                return "https://renderdoc.org" + href
            return "https://renderdoc.org/" + href
    raise ValueError("RenderDoc v1.44 Windows x64 installer link was not found")


class RenderDocInstaller:
    def __init__(
        self,
        config: AppConfig,
        finder: Callable[[], dict[str, str]] = find_renderdoc_install,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ):
        self.config = config
        self.finder = finder
        self.runner = runner

    def ensure_installed(self) -> bool:
        found = self.finder()
        if found.get("qrenderdoc_path"):
            self.config.renderdoc.version = RENDERDOC_VERSION
            self.config.renderdoc.install_dir = found.get("install_dir", "")
            self.config.renderdoc.qrenderdoc_path = found.get("qrenderdoc_path", "")
            self.config.renderdoc.renderdoccmd_path = found.get("renderdoccmd_path", "")
            return True
        return False

    def resolve_download_url(self) -> str:
        with urllib.request.urlopen(BUILDS_URL, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
        return parse_v144_windows_x64_url(html)

    def download_installer(self, url: str) -> Path:
        downloads = app_data_dir() / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        filename = url.rstrip("/").split("/")[-1] or "RenderDoc_1.44_64_installer.exe"
        target = downloads / filename
        urllib.request.urlretrieve(url, target)
        return target

    def run_installer(self, installer_path: Path) -> None:
        suffix = installer_path.suffix.lower()
        if suffix == ".msi":
            self.runner(["msiexec", "/i", str(installer_path), "/passive"], check=True)
            return
        self.runner([str(installer_path)], check=True)
