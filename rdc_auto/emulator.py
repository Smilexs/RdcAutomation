from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from .config import AppConfig
from .paths import validate_mumu_root
from .processes import hidden_console_kwargs, tasklist_count_from_csv


Runner = Callable[..., subprocess.CompletedProcess[str]]


class EmulatorProcess:
    def __init__(self, runner: Runner = subprocess.run):
        self._runner = runner

    def is_running(self, image_name: str) -> bool:
        result = self._runner(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_console_kwargs(),
        )
        return tasklist_count_from_csv(result.stdout, image_name) > 0

    def terminate_tree(self, image_name: str) -> None:
        result = self._runner(
            ["taskkill", "/IM", image_name, "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_console_kwargs(),
        )
        if result.returncode != 0:
            details = "\n".join(part for part in [result.stderr, result.stdout] if part)
            raise RuntimeError(f"Failed to terminate {image_name}: {details}")

    def wait_until_running(self, image_name: str, timeout_seconds: float) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self.is_running(image_name):
                return
            time.sleep(0.5)
        raise TimeoutError(f"Timed out waiting for process to start: {image_name}")


class MuMu12:
    image_name = "MuMuNxMain.exe"
    render_target_name = "MuMuVMHeadless"

    def __init__(self, config: AppConfig, process: EmulatorProcess | None = None):
        self.config = config
        self.process = process or EmulatorProcess()

    def executable(self) -> Path:
        if not self.config.emulator.root_dir:
            raise FileNotFoundError("MuMu12 root directory is not configured")
        return validate_mumu_root(self.config.emulator.root_dir, self.config.emulator.exe_relative_path)

    def launch_spec(self) -> dict[str, Path | str]:
        exe = self.executable()
        manager = self._manager_executable(exe)
        if manager is None:
            return {"exe_path": exe, "working_dir": exe.parent, "cmd_line": ""}

        vm_index = getattr(self.config.emulator, "vm_index", "").strip() or "0"
        return {
            "exe_path": manager,
            "working_dir": manager.parent,
            "cmd_line": f"control -v {vm_index} launch",
        }

    def target_process_name(self) -> str:
        return self.render_target_name

    def is_running(self) -> bool:
        return self.process.is_running(self.image_name)

    def terminate(self) -> None:
        self.process.terminate_tree(self.image_name)

    def wait_until_running(self, timeout_seconds: float) -> None:
        self.process.wait_until_running(self.image_name, timeout_seconds)

    def _manager_executable(self, exe: Path) -> Path | None:
        player_root = exe.parent.parent
        candidates = [
            exe.parent / "MuMuManager.exe",
            player_root / "shell" / "MuMuManager.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None
