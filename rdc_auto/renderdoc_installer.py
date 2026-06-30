from __future__ import annotations

import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable

from .config import AppConfig, app_data_dir
from .errors import DependencyMissing
from .paths import find_renderdoc_install, renderdoc_install_from_qrenderdoc


BUILDS_URL = "https://renderdoc.org/builds"
RENDERDOC_VERSION = "1.44"


def parse_v144_windows_x64_url(html: str) -> str:
    hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    for href in hrefs:
        lower = href.lower()
        if (
            re.search(r"(?<!\d)1\.44(?!\d)", lower)
            and ("_64" in lower or "x64" in lower)
            and (lower.endswith(".msi") or lower.endswith(".exe"))
        ):
            if href.startswith("http://") or href.startswith("https://"):
                return href
            if href.startswith("/"):
                return "https://renderdoc.org" + href
            return "https://renderdoc.org/" + href
    raise ValueError("RenderDoc v1.44 Windows x64 installer link was not found")


def parse_renderdoc_version(text: str) -> str:
    match = re.search(r"(?<!\d)v?(\d+)\.(\d+)(?:\.\d+)?", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return f"{match.group(1)}.{match.group(2)}"


class RenderDocInstaller:
    def __init__(
        self,
        config: AppConfig,
        finder: Callable[[], dict[str, str]] = find_renderdoc_install,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
        version_reader: Callable[[dict[str, str]], str] | None = None,
    ):
        self.config = config
        self.finder = finder
        self.runner = runner
        self.version_reader = version_reader or self._read_installed_version

    def ensure_installed(self) -> bool:
        configured_qrenderdoc = self.config.renderdoc.qrenderdoc_path.strip()
        found = renderdoc_install_from_qrenderdoc(configured_qrenderdoc) if configured_qrenderdoc else self.finder()
        if found.get("qrenderdoc_path"):
            detected_version = self.version_reader(found)
            self.config.renderdoc.version = detected_version
            if detected_version != RENDERDOC_VERSION:
                self.config.renderdoc.install_dir = ""
                self.config.renderdoc.qrenderdoc_path = ""
                self.config.renderdoc.renderdoccmd_path = ""
                if configured_qrenderdoc:
                    version_label = detected_version or "unknown"
                    raise DependencyMissing(
                        f"Configured RenderDoc version is {version_label}, but v{RENDERDOC_VERSION} is required: "
                        f"{configured_qrenderdoc}"
                    )
                return False
            self.config.renderdoc.version = RENDERDOC_VERSION
            self.config.renderdoc.install_dir = found.get("install_dir", "")
            self.config.renderdoc.qrenderdoc_path = found.get("qrenderdoc_path", "")
            self.config.renderdoc.renderdoccmd_path = found.get("renderdoccmd_path", "")
            return True
        return False

    def _read_installed_version(self, found: dict[str, str]) -> str:
        for key in ("renderdoccmd_path", "qrenderdoc_path"):
            exe = found.get(key)
            if not exe:
                continue
            try:
                result = self.runner(
                    [exe, "--version"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            output = f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}"
            version = parse_renderdoc_version(output)
            if version:
                return version
        return ""

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
