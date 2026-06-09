from __future__ import annotations

import csv
import subprocess
from io import StringIO
from pathlib import Path
from typing import Callable

from .config import AppConfig
from .paths import validate_mumu_root


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
        )
        rows = csv.DictReader(StringIO(result.stdout))
        for row in rows:
            if row.get("Image Name", "").lower() == image_name.lower():
                return True
        return False

    def terminate_tree(self, image_name: str) -> None:
        result = self._runner(["taskkill", "/IM", image_name, "/T", "/F"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            details = "\n".join(part for part in [result.stderr, result.stdout] if part)
            raise RuntimeError(f"Failed to terminate {image_name}: {details}")


class MuMu12:
    image_name = "MuMuNxMain.exe"

    def __init__(self, config: AppConfig, process: EmulatorProcess | None = None):
        self.config = config
        self.process = process or EmulatorProcess()

    def executable(self) -> Path:
        if not self.config.emulator.root_dir:
            raise FileNotFoundError("MuMu12 root directory is not configured")
        return validate_mumu_root(self.config.emulator.root_dir, self.config.emulator.exe_relative_path)

    def is_running(self) -> bool:
        return self.process.is_running(self.image_name)

    def terminate(self) -> None:
        self.process.terminate_tree(self.image_name)
