from __future__ import annotations

import subprocess

from rdc_auto.processes import count_processes, is_process_running, tasklist_count_from_csv


def test_tasklist_count_from_csv_counts_matching_rows():
    stdout = '"Image Name","PID"\n"qrenderdoc.exe","10"\n"notepad.exe","11"\n"qrenderdoc.exe","12"\n'

    assert tasklist_count_from_csv(stdout, "qrenderdoc.exe") == 2


def test_is_process_running_uses_runner():
    def runner(args, capture_output, text, check):
        return subprocess.CompletedProcess(args, 0, stdout='"Image Name","PID"\n"RenderDocMCP.exe","20"\n')

    assert count_processes("RenderDocMCP.exe", runner=runner) == 1
    assert is_process_running("RenderDocMCP.exe", runner=runner) is True
