from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import urllib.request

from .config import AppConfig, app_data_dir


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    digest: str = ""


def parse_release_asset(release: dict) -> ReleaseAsset:
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        lower = name.lower()
        if lower.startswith("renderdocmcp-setup-") and lower.endswith(".exe"):
            return ReleaseAsset(
                name=name,
                download_url=str(asset["browser_download_url"]),
                digest=str(asset.get("digest", "")),
            )
    raise ValueError("No RenderDocMCP setup .exe asset was found in the latest release")


JsonFetcher = Callable[[str], dict]
Downloader = Callable[[str, Path], object]
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


class McpInstaller:
    def __init__(
        self,
        config: AppConfig,
        fetch_json: JsonFetcher | None = None,
        downloader: Callable[[str, Path], object] | None = None,
        runner: Runner = subprocess.run,
    ):
        self.config = config
        self.fetch_json = fetch_json or self._fetch_json
        self.downloader = downloader or self._download
        self.runner = runner

    @staticmethod
    def _fetch_json(url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": "rdc-auto"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _download(url: str, target: Path) -> object:
        target.parent.mkdir(parents=True, exist_ok=True)
        return urllib.request.urlretrieve(url, target)

    def download_latest_installer(self) -> Path:
        release = self.fetch_json(self.config.mcp.release_api_url)
        asset = parse_release_asset(release)
        downloads = Path(self.config.mcp.install_dir or app_data_dir() / "mcp") / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        target = downloads / asset.name
        self.downloader(asset.download_url, target)
        self.config.mcp.asset_name = asset.name
        self.config.mcp.installer_path = str(target)
        return target

    def run_installer(self, installer_path: Path) -> None:
        self.runner([str(installer_path)], check=True)

    def discover_executable(self) -> Path | None:
        configured = Path(self.config.mcp.executable_path) if self.config.mcp.executable_path else None
        if configured and configured.is_file():
            return configured

        candidates = []
        install_dir = Path(self.config.mcp.install_dir) if self.config.mcp.install_dir else app_data_dir() / "mcp"
        for root in [
            install_dir,
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "RenderDocMCP",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "RenderDocMCP",
        ]:
            if str(root):
                candidates.extend([root / "RenderDocMCP.exe", root / "renderdoc-mcp.exe"])

        for candidate in candidates:
            if candidate.is_file():
                self.config.mcp.executable_path = str(candidate)
                return candidate
        return None

    def ensure_installed(self) -> Path:
        existing = self.discover_executable()
        if existing:
            return existing
        installer = self.download_latest_installer()
        self.run_installer(installer)
        found = self.discover_executable()
        if not found:
            raise FileNotFoundError("RenderDocMCP installed, but its executable was not found. Set mcp.executable_path in config.json.")
        return found
