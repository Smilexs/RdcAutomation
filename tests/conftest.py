from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path / "LocalAppData")
    env["TEMP"] = str(tmp_path / "Temp")
    env["TMP"] = str(tmp_path / "Temp")
    return env
