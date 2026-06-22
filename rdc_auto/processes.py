from __future__ import annotations

import csv
import subprocess
from io import StringIO
from pathlib import Path
from typing import Callable

from .errors import RdcAutoError


Runner = Callable[..., subprocess.CompletedProcess[str]]


def tasklist_count_from_csv(stdout: str, image_name: str) -> int:
    target = image_name.lower()
    rows = csv.reader(StringIO(stdout))
    count = 0
    for row in rows:
        if not row:
            continue
        if row[0].strip().lower() == target:
            count += 1
    return count


def count_processes(image_name: str, runner: Runner = subprocess.run) -> int:
    try:
        result = runner(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 0
    return tasklist_count_from_csv(result.stdout, image_name)


def is_process_running(image_name: str, runner: Runner = subprocess.run) -> bool:
    return count_processes(image_name, runner=runner) > 0


def terminate_process_tree(image_name: str, runner: Runner = subprocess.run) -> None:
    try:
        result = runner(
            ["taskkill", "/IM", image_name, "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    if result.returncode != 0 and count_processes(image_name, runner=runner) > 0:
        details = "\n".join(part for part in [result.stderr, result.stdout] if part).strip()
        raise RdcAutoError(f"Failed to stop stale RenderDocMCP bridge process {image_name}: {details}")


def executable_name(path: str | Path) -> str:
    return Path(path).name
