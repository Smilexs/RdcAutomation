from __future__ import annotations

import csv
import subprocess
import sys
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


def tasklist_ids_from_csv(stdout: str, image_name: str) -> set[int]:
    target = image_name.lower()
    rows = csv.reader(StringIO(stdout))
    pids: set[int] = set()
    for row in rows:
        if len(row) < 2:
            continue
        if row[0].strip().lower() != target:
            continue
        try:
            pids.add(int(row[1].strip()))
        except ValueError:
            continue
    return pids


def count_processes(image_name: str, runner: Runner = subprocess.run) -> int:
    try:
        result = runner(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_console_kwargs(),
        )
    except OSError:
        return 0
    return tasklist_count_from_csv(result.stdout, image_name)


def process_ids(image_name: str, runner: Runner = subprocess.run) -> set[int]:
    try:
        result = runner(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_console_kwargs(),
        )
    except OSError:
        return set()
    return tasklist_ids_from_csv(result.stdout, image_name)


def is_process_running(image_name: str, runner: Runner = subprocess.run) -> bool:
    return count_processes(image_name, runner=runner) > 0


def terminate_process_tree(image_name: str, runner: Runner = subprocess.run) -> None:
    try:
        result = runner(
            ["taskkill", "/IM", image_name, "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_console_kwargs(),
        )
    except OSError:
        return
    if result.returncode != 0 and count_processes(image_name, runner=runner) > 0:
        details = "\n".join(part for part in [result.stderr, result.stdout] if part).strip()
        raise RdcAutoError(f"Failed to stop process {image_name}: {details}")


def terminate_process_tree_by_pid(pid: int, runner: Runner = subprocess.run) -> None:
    try:
        result = runner(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_console_kwargs(),
        )
    except (OSError, ValueError):
        return
    if result.returncode != 0:
        details = "\n".join(part for part in [result.stderr, result.stdout] if part).strip()
        raise RdcAutoError(f"Failed to stop process PID {pid}: {details}")


def executable_name(path: str | Path) -> str:
    return Path(path).name


def hidden_console_kwargs() -> dict:
    if not sys.platform.startswith("win"):
        return {}

    kwargs = {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if creationflags:
        kwargs["creationflags"] = creationflags

    startupinfo_type = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_type is not None:
        startupinfo = startupinfo_type()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo

    return kwargs
