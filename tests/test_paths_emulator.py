from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rdc_auto.config import AppConfig
from rdc_auto.emulator import EmulatorProcess, MuMu12
from rdc_auto.paths import mumu_exe_path, validate_mumu_root


def test_mumu_exe_path_uses_fixed_relative_path():
    assert mumu_exe_path(Path("D:/MuMu")) == Path("D:/MuMu/MuMuPlayer-12.0/nx_main/MuMuNxMain.exe")


def test_validate_mumu_root_accepts_existing_exe(tmp_path):
    exe = tmp_path / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    assert validate_mumu_root(tmp_path) == exe


def test_canonical_mumu_root_accepts_nested_mumu_paths(tmp_path):
    from rdc_auto import paths

    root = tmp_path / "MuMu12"
    exe = root / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")

    assert paths.canonical_mumu_root(root) == root
    assert paths.canonical_mumu_root(root / "MuMuPlayer-12.0") == root
    assert paths.canonical_mumu_root(root / "MuMuPlayer-12.0" / "nx_main") == root


def test_validate_mumu_root_rejects_missing_exe(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_mumu_root(tmp_path)


def test_emulator_running_detects_tasklist_csv():
    calls = []

    def runner(args, capture_output, text, check, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout='"Image Name","PID"\n"MuMuNxMain.exe","1234"\n')

    proc = EmulatorProcess(runner=runner)

    assert proc.is_running("MuMuNxMain.exe") is True
    assert calls[0][0] == "tasklist"


def test_emulator_running_detects_tasklist_csv_without_english_header():
    def runner(args, capture_output, text, check, **kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            stdout='"映像名称","PID","会话名","会话#","内存使用"\n"MuMuNxMain.exe","1234","Console","1","10,000 K"\n',
        )

    proc = EmulatorProcess(runner=runner)

    assert proc.is_running("MuMuNxMain.exe") is True


def test_emulator_process_queries_hide_windows_on_windows():
    kwargs_seen = []

    def runner(args, capture_output, text, check, **kwargs):
        kwargs_seen.append(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout='"Image Name","PID"\n')

    EmulatorProcess(runner=runner).is_running("MuMuNxMain.exe")

    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert kwargs_seen[0]["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_terminate_tree_raises_when_taskkill_fails():
    calls = []

    def runner(args, capture_output, text, check, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, stdout="not found", stderr="access denied")

    proc = EmulatorProcess(runner=runner)

    with pytest.raises(RuntimeError) as excinfo:
        proc.terminate_tree("MuMuNxMain.exe")

    assert calls[0] == ["taskkill", "/IM", "MuMuNxMain.exe", "/T", "/F"]
    message = str(excinfo.value)
    assert "MuMuNxMain.exe" in message
    assert "access denied" in message
    assert "not found" in message


def test_mumu12_resolve_updates_config(tmp_path):
    exe = tmp_path / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path)

    mumu = MuMu12(cfg)

    assert mumu.executable() == exe


def test_mumu12_executable_uses_configured_relative_path(tmp_path):
    exe = tmp_path / "CustomMuMu" / "bin" / "CustomMain.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path)
    cfg.emulator.exe_relative_path = "CustomMuMu/bin/CustomMain.exe"

    mumu = MuMu12(cfg)

    assert mumu.executable() == exe


def test_mumu12_launch_spec_uses_mumu_manager_for_configured_vm_index(tmp_path):
    main_exe = tmp_path / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    manager_exe = main_exe.parent / "MuMuManager.exe"
    main_exe.parent.mkdir(parents=True)
    main_exe.write_text("", encoding="utf-8")
    manager_exe.write_text("", encoding="utf-8")
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path)
    cfg.emulator.vm_index = "1"

    spec = MuMu12(cfg).launch_spec()

    assert spec["exe_path"] == manager_exe
    assert spec["working_dir"] == manager_exe.parent
    assert spec["cmd_line"] == "control -v 1 launch"


def test_mumu12_launch_spec_defaults_to_manager_vm_zero(tmp_path):
    main_exe = tmp_path / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    manager_exe = main_exe.parent / "MuMuManager.exe"
    main_exe.parent.mkdir(parents=True)
    main_exe.write_text("", encoding="utf-8")
    manager_exe.write_text("", encoding="utf-8")
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path)

    spec = MuMu12(cfg).launch_spec()

    assert spec["exe_path"] == manager_exe
    assert spec["working_dir"] == manager_exe.parent
    assert spec["cmd_line"] == "control -v 0 launch"


def test_mumu12_launch_spec_finds_shell_mumu_manager(tmp_path):
    main_exe = tmp_path / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    manager_exe = tmp_path / "MuMuPlayer-12.0" / "shell" / "MuMuManager.exe"
    main_exe.parent.mkdir(parents=True)
    manager_exe.parent.mkdir(parents=True)
    main_exe.write_text("", encoding="utf-8")
    manager_exe.write_text("", encoding="utf-8")
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path)
    cfg.emulator.vm_index = "2"

    spec = MuMu12(cfg).launch_spec()

    assert spec["exe_path"] == manager_exe
    assert spec["working_dir"] == manager_exe.parent
    assert spec["cmd_line"] == "control -v 2 launch"
