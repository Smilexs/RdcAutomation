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

    def runner(args, capture_output, text, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout='"Image Name","PID"\n"MuMuNxMain.exe","1234"\n')

    proc = EmulatorProcess(runner=runner)

    assert proc.is_running("MuMuNxMain.exe") is True
    assert calls[0][0] == "tasklist"


def test_terminate_tree_raises_when_taskkill_fails():
    calls = []

    def runner(args, capture_output, text, check):
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


def test_mumu12_launch_spec_uses_mumu_cli_for_configured_vm_index(tmp_path):
    main_exe = tmp_path / "MuMuPlayer-12.0" / "nx_main" / "MuMuNxMain.exe"
    cli_exe = main_exe.parent / "mumu-cli.exe"
    main_exe.parent.mkdir(parents=True)
    main_exe.write_text("", encoding="utf-8")
    cli_exe.write_text("", encoding="utf-8")
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path)
    cfg.emulator.vm_index = "1"

    spec = MuMu12(cfg).launch_spec()

    assert spec["exe_path"] == cli_exe
    assert spec["working_dir"] == cli_exe.parent
    assert spec["cmd_line"] == "control --vmindex 1 launch"
