from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


APP_DIR_NAME = "RdcAutomation"
MCP_RELEASE_API_URL = "https://api.github.com/repos/Smilexs/RenderDocMCP/releases/latest"
MUMU_RELATIVE_EXE = "MuMuPlayer-12.0\\nx_main\\MuMuNxMain.exe"


@dataclass
class RenderDocConfig:
    version: str = "1.44"
    install_dir: str = ""
    qrenderdoc_path: str = ""
    renderdoccmd_path: str = ""


@dataclass
class McpConfig:
    release_api_url: str = MCP_RELEASE_API_URL
    release_tag: str = ""
    asset_name: str = ""
    asset_digest: str = ""
    installer_path: str = ""
    install_dir: str = ""
    executable_path: str = ""
    mode: str = "managed"
    extension_patch_restart_required: bool = False


@dataclass
class EmulatorConfig:
    type: str = "mumu12"
    root_dir: str = ""
    exe_relative_path: str = MUMU_RELATIVE_EXE
    graphics_api: str = "vulkan"
    vm_index: str = ""


@dataclass
class CaptureConfig:
    last_output_dir: str = ""
    last_rdc_path: str = ""
    active_session_id: str | None = None
    active_launch_id: str = ""
    active_pid: int | None = None
    active_session_started_at: str | None = None


@dataclass
class GuiConfig:
    window_width: int = 1320
    window_height: int = 860
    last_view: str = "dashboard"


@dataclass
class AiConfig:
    provider: str = "openai"
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""


@dataclass
class AppConfig:
    renderdoc: RenderDocConfig = field(default_factory=RenderDocConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    emulator: EmulatorConfig = field(default_factory=EmulatorConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)
    ai: AiConfig = field(default_factory=AiConfig)

    @classmethod
    def default(cls) -> "AppConfig":
        cfg = cls()
        app_dir = app_data_dir()
        cfg.mcp.install_dir = str(app_dir / "mcp")
        return cfg


def app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME


def log_dir() -> Path:
    return app_data_dir() / "logs"


def config_path() -> Path:
    return app_data_dir() / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    path = path or config_path()
    if not path.exists():
        return AppConfig.default()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _from_dict(raw)


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _from_dict(raw: dict[str, Any]) -> AppConfig:
    default = AppConfig.default()
    return AppConfig(
        renderdoc=RenderDocConfig(**{**asdict(default.renderdoc), **raw.get("renderdoc", {})}),
        mcp=McpConfig(**{**asdict(default.mcp), **raw.get("mcp", {})}),
        emulator=EmulatorConfig(**{**asdict(default.emulator), **raw.get("emulator", {})}),
        capture=CaptureConfig(**{**asdict(default.capture), **raw.get("capture", {})}),
        gui=GuiConfig(**{**asdict(default.gui), **raw.get("gui", {})}),
        ai=AiConfig(**{**asdict(default.ai), **raw.get("ai", {})}),
    )
