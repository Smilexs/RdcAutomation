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
        vm_index = getattr(self.config.emulator, "vm_index", "").strip()
        if not vm_index:
            return {"exe_path": exe, "working_dir": exe.parent, "cmd_line": ""}

        mumu_cli = exe.parent / "mumu-cli.exe"
        if not mumu_cli.is_file():
            raise FileNotFoundError(f"MuMu12 CLI executable not found: {mumu_cli}")
        return {
            "exe_path": mumu_cli,
            "working_dir": mumu_cli.parent,
            "cmd_line": f"control --vmindex {vm_index} launch",
        }

    def target_process_name(self) -> str:
        return self.render_target_name

    def is_running(self) -> bool:
        return self.process.is_running(self.image_name)

    def terminate(self) -> None:
        self.process.terminate_tree(self.image_name)
