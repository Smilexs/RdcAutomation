from __future__ import annotations

import sys
from pathlib import Path


def package_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        return Path(bundle_root)
    return Path(__file__).resolve().parents[2]


def gui_static_dir() -> Path:
    bundled = package_root() / "rdc_auto" / "gui" / "static"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parent / "static"


def gui_index_path() -> Path:
    return gui_static_dir() / "index.html"
