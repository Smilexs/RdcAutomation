from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Callable, Iterable

from .config import AppConfig, app_data_dir
from .errors import DependencyMissing


JsonFetcher = Callable[[str], dict]
Downloader = Callable[[str, Path], object]
Runner = Callable[..., subprocess.CompletedProcess[bytes]]

SOURCE_DIRNAME = "renderdoc_mcp"
EXTENSION_SOURCE_DIRNAME = "renderdoc_extension"
MCP_SERVER_DIRNAME = "mcp_server"
INSTALLED_EXTENSION_DIRNAME = "renderdoc_mcp_bridge"
ALWAYS_LOAD_KEY = "AlwaysLoad_Extensions"


class McpInstaller:
    def __init__(
        self,
        config: AppConfig,
        fetch_json: JsonFetcher | None = None,
        downloader: Callable[[str, Path], object] | None = None,
        runner: Runner = subprocess.run,
        local_installer_dirs: Iterable[str | Path] | None = None,
        source_roots: Iterable[str | Path] | None = None,
    ):
        self.config = config
        self.fetch_json = fetch_json or (lambda url: {})
        self.downloader = downloader or (lambda url, target: None)
        self.runner = runner
        self.local_installer_dirs = [Path(path) for path in local_installer_dirs or []]
        self.source_roots = (
            [Path(path) for path in source_roots]
            if source_roots is not None
            else _default_source_roots(config)
        )

    def ensure_installed(self) -> Path:
        source_root = self.source_root()
        installed_source = self._sync_source(source_root)
        extension_dir = self._install_extension(installed_source / EXTENSION_SOURCE_DIRNAME)
        self.config.mcp.source_path = str(installed_source)
        self.config.mcp.extension_dir = str(extension_dir)
        self.config.mcp.executable_path = ""
        self.config.mcp.installer_path = ""
        self.config.mcp.asset_name = "RenderDocMCP source"
        self.config.mcp.asset_digest = ""
        self.config.mcp.release_tag = _source_version(installed_source)
        return extension_dir

    def source_root(self) -> Path:
        for root in _unique_paths(self.source_roots):
            if _valid_source_root(root):
                return root
        searched = ", ".join(str(path) for path in self.source_roots)
        raise DependencyMissing(f"Bundled RenderDocMCP source was not found. Searched: {searched}")

    def discover_extension(self, allow_configured: bool = True) -> Path | None:
        configured = Path(self.config.mcp.extension_dir) if self.config.mcp.extension_dir else None
        if configured and _valid_installed_extension(configured):
            return configured
        if configured and allow_configured:
            raise DependencyMissing(f"Configured RenderDocMCP extension was not found: {configured}")

        candidates: list[Path] = []
        if self.config.mcp.executable_path:
            executable = Path(self.config.mcp.executable_path)
            candidates.append(executable.parent / EXTENSION_SOURCE_DIRNAME)
        if self.config.mcp.source_path:
            source = Path(self.config.mcp.source_path)
            candidates.append(source / EXTENSION_SOURCE_DIRNAME)
        candidates.append(_default_renderdoc_extensions_dir() / INSTALLED_EXTENSION_DIRNAME)

        for candidate in _unique_paths(candidates):
            if _valid_installed_extension(candidate):
                self.config.mcp.extension_dir = str(candidate)
                return candidate
        return None

    def runtime_extension_dir(self) -> Path:
        found = self.discover_extension(allow_configured=True)
        if found:
            return found
        raise DependencyMissing("RenderDocMCP extension was not found. Run rdc-auto setup.")

    def discover_executable(self, allow_configured: bool = True) -> Path | None:
        configured = Path(self.config.mcp.executable_path) if self.config.mcp.executable_path else None
        if configured and configured.is_file():
            return configured
        if configured and allow_configured:
            raise DependencyMissing(f"Configured RenderDocMCP executable was not found: {configured}")
        return None

    def runtime_executable(self) -> Path:
        found = self.discover_executable(allow_configured=True)
        if found:
            return found
        raise DependencyMissing("RenderDocMCP executable is no longer used. Run rdc-auto setup to install the embedded extension.")

    def _sync_source(self, source_root: Path) -> Path:
        install_dir = Path(self.config.mcp.install_dir or app_data_dir() / "mcp")
        target = install_dir / SOURCE_DIRNAME
        if source_root.resolve() == target.resolve():
            return target
        if target.exists():
            shutil.rmtree(target)
        _copy_source_tree(source_root, target)
        return target

    def _install_extension(self, extension_source: Path) -> Path:
        if not _valid_installed_extension(extension_source):
            raise DependencyMissing(f"Bundled RenderDocMCP extension source is incomplete: {extension_source}")
        extension_root = _default_renderdoc_extensions_dir()
        extension_dir = extension_root / INSTALLED_EXTENSION_DIRNAME
        if extension_dir.exists():
            shutil.rmtree(extension_dir)
        _copy_source_tree(extension_source, extension_dir)
        _configure_always_load(extension_root, enabled=True)
        return extension_dir


def _default_source_roots(config: AppConfig) -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(Path(meipass) / SOURCE_DIRNAME)
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent / SOURCE_DIRNAME)
    roots.append(Path.cwd() / SOURCE_DIRNAME)
    roots.append(Path(__file__).resolve().parents[1] / SOURCE_DIRNAME)
    if config.mcp.source_path:
        roots.append(Path(config.mcp.source_path))
    install_dir = Path(config.mcp.install_dir) if config.mcp.install_dir else app_data_dir() / "mcp"
    roots.append(install_dir / SOURCE_DIRNAME)
    return _unique_paths(roots)


def _default_renderdoc_extensions_dir() -> Path:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "qrenderdoc" / "extensions"
        return Path.home() / "AppData" / "Roaming" / "qrenderdoc" / "extensions"
    return Path.home() / ".local" / "share" / "qrenderdoc" / "extensions"


def _valid_source_root(path: Path) -> bool:
    return (
        (path / EXTENSION_SOURCE_DIRNAME / "extension.json").is_file()
        and (path / MCP_SERVER_DIRNAME / "server.py").is_file()
    )


def _valid_installed_extension(path: Path) -> bool:
    return (path / "extension.json").is_file()


def _copy_source_tree(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"),
    )


def _configure_always_load(extension_root: Path, enabled: bool) -> None:
    config_path = extension_root.parent / "UI.config"
    data = _read_ui_config(config_path, create_if_missing=enabled)
    if data is None:
        return

    entries = data.get(ALWAYS_LOAD_KEY)
    if not isinstance(entries, list):
        entries = []
        data[ALWAYS_LOAD_KEY] = entries

    changed = False
    if enabled and INSTALLED_EXTENSION_DIRNAME not in entries:
        entries.append(INSTALLED_EXTENSION_DIRNAME)
        changed = True
    elif not enabled and INSTALLED_EXTENSION_DIRNAME in entries:
        data[ALWAYS_LOAD_KEY] = [entry for entry in entries if entry != INSTALLED_EXTENSION_DIRNAME]
        changed = True

    if changed or not config_path.exists():
        _write_ui_config(config_path, data)


def _read_ui_config(config_path: Path, create_if_missing: bool) -> dict | None:
    if not config_path.exists():
        return {} if create_if_missing else None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyMissing(f"Failed to read RenderDoc UI config: {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise DependencyMissing(f"RenderDoc UI config must contain a JSON object: {config_path}")
    return data


def _write_ui_config(config_path: Path, data: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = config_path.with_name(config_path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    tmp_path.replace(config_path)


def _source_version(source_root: Path) -> str:
    pyproject = source_root / "pyproject.toml"
    if not pyproject.is_file():
        return "embedded"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return "embedded"
    version = str(data.get("project", {}).get("version", "")).strip()
    return f"v{version}" if version else "embedded"


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path.absolute())
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        unique.append(path)
    return unique
