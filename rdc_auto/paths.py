from __future__ import annotations

import os
from pathlib import Path

from .config import MUMU_RELATIVE_EXE


def mumu_exe_path(root: str | Path, relative_exe: str | Path = MUMU_RELATIVE_EXE) -> Path:
    return Path(root) / Path(relative_exe)


def validate_mumu_root(root: str | Path, relative_exe: str | Path = MUMU_RELATIVE_EXE) -> Path:
    exe = mumu_exe_path(root, relative_exe)
    if not exe.is_file():
        raise FileNotFoundError(f"MuMu12 executable not found: {exe}")
    return exe


def find_renderdoc_install() -> dict[str, str]:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "RenderDoc",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "RenderDoc",
    ]
    for install_dir in candidates:
        qrenderdoc = install_dir / "qrenderdoc.exe"
        renderdoccmd = install_dir / "renderdoccmd.exe"
        if qrenderdoc.is_file():
            return {
                "install_dir": str(install_dir),
                "qrenderdoc_path": str(qrenderdoc),
                "renderdoccmd_path": str(renderdoccmd) if renderdoccmd.is_file() else "",
            }
    return {"install_dir": "", "qrenderdoc_path": "", "renderdoccmd_path": ""}
