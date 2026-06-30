from __future__ import annotations

import subprocess

from rdc_auto.processes import (
    count_processes,
    is_process_running,
    process_ids,
    tasklist_count_from_csv,
    tasklist_ids_from_csv,
    terminate_process_tree_by_pid,
)


def test_tasklist_count_from_csv_counts_matching_rows():
    stdout = '"Image Name","PID"\n"qrenderdoc.exe","10"\n"notepad.exe","11"\n"qrenderdoc.exe","12"\n'

    assert tasklist_count_from_csv(stdout, "qrenderdoc.exe") == 2


def test_tasklist_ids_from_csv_returns_matching_pids():
    stdout = '"Image Name","PID"\n"qrenderdoc.exe","10"\n"notepad.exe","11"\n"qrenderdoc.exe","12"\n'

    assert tasklist_ids_from_csv(stdout, "qrenderdoc.exe") == {10, 12}


def test_is_process_running_uses_runner():
    def runner(args, capture_output, text, check, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout='"Image Name","PID"\n"RenderDocMCP.exe","20"\n')

    assert count_processes("RenderDocMCP.exe", runner=runner) == 1
    assert is_process_running("RenderDocMCP.exe", runner=runner) is True


def test_process_ids_uses_runner():
    def runner(args, capture_output, text, check, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout='"Image Name","PID"\n"RenderDocMCP.exe","20"\n')

    assert process_ids("RenderDocMCP.exe", runner=runner) == {20}


def test_terminate_process_tree_by_pid_uses_taskkill_pid():
    calls = []

    def runner(args, capture_output, text, check, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    terminate_process_tree_by_pid(303, runner=runner)

    assert calls == [["taskkill", "/PID", "303", "/T", "/F"]]
