from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

from rdc_auto.config import AppConfig, load_config
from rdc_auto.errors import McpCapabilityMissing, UserActionRequired
from rdc_auto.gui.bridge import GuiBridge
from rdc_auto.gui.status import McpRuntimeProbe, build_status_snapshot


def test_build_status_snapshot_contains_topbar_sections(tmp_path):
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(tmp_path / "qrenderdoc.exe")
    cfg.mcp.executable_path = str(tmp_path / "RenderDocMCP.exe")
    mumu_root = tmp_path / "MuMu"
    mumu_exe = mumu_root / "nx_main" / "MuMuNxMain.exe"
    mumu_exe.parent.mkdir(parents=True)
    mumu_exe.write_bytes(b"exe")
    cfg.emulator.root_dir = str(mumu_root)
    cfg.capture.active_launch_id = "launch-1"

    snapshot = build_status_snapshot(cfg, process_counts={"qrenderdoc.exe": 1})

    assert snapshot["renderdoc"]["path"].endswith("qrenderdoc.exe")
    assert snapshot["mumu"]["ready"] is True
    assert snapshot["mumu"]["invalid_reason"] == ""
    assert snapshot["mcp"]["running"] is True
    assert snapshot["session"]["attached"] is True
    assert snapshot["session"]["launch_id"] == "launch-1"
    assert snapshot["config_preview"]["capture"]["active_launch_id"] == "launch-1"


def test_build_status_snapshot_marks_unset_mumu_root_invalid():
    cfg = AppConfig.default()

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["mumu"]["ready"] is False
    assert snapshot["mumu"]["invalid_reason"] == "MuMu12 root directory is not configured"


def test_build_status_snapshot_marks_unset_tool_paths_invalid():
    cfg = AppConfig.default()

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["renderdoc"]["ready"] is False
    assert snapshot["renderdoc"]["invalid_reason"] == "qrenderdoc.exe path is not configured"
    assert snapshot["mcp"]["ready"] is False
    assert snapshot["mcp"]["invalid_reason"] == "RenderDocMCP extension is not configured"


def test_build_status_snapshot_marks_missing_tool_paths_invalid(tmp_path):
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(tmp_path / "missing" / "qrenderdoc.exe")
    cfg.mcp.executable_path = str(tmp_path / "missing" / "RenderDocMCP.exe")

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["renderdoc"]["ready"] is False
    assert "qrenderdoc.exe was not found" in snapshot["renderdoc"]["invalid_reason"]
    assert snapshot["mcp"]["ready"] is False
    assert "RenderDocMCP executable was not found" in snapshot["mcp"]["invalid_reason"]


def test_build_status_snapshot_validates_mumu_root(tmp_path):
    cfg = AppConfig.default()
    cfg.emulator.root_dir = str(tmp_path / "missing-mumu")

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["mumu"]["ready"] is False
    assert "MuMu12 executable not found" in snapshot["mumu"]["invalid_reason"]


def test_build_status_snapshot_empty_process_counts_are_authoritative(monkeypatch):
    cfg = AppConfig.default()

    def fail_count_processes(name: str) -> int:
        raise AssertionError(f"unexpected live process probe for {name}")

    monkeypatch.setattr("rdc_auto.gui.status.count_processes", fail_count_processes)

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["mcp"]["running"] is False
    assert snapshot["mcp"]["extension_loaded"] is False


def test_build_status_snapshot_uses_mcp_probe_over_qrenderdoc_process_guess(tmp_path):
    cfg = AppConfig.default()
    cfg.mcp.executable_path = str(tmp_path / "RenderDocMCP.exe")

    snapshot = build_status_snapshot(
        cfg,
        process_counts={"qrenderdoc.exe": 1, "RenderDocMCP.exe": 0, "renderdoc-mcp.exe": 0},
        mcp_runtime=McpRuntimeProbe(process_running=True, reachable=False, detail="ping timeout"),
    )

    assert snapshot["mcp"]["running"] is False
    assert snapshot["mcp"]["extension_loaded"] is False
    assert snapshot["mcp"]["runtime_detail"] == "ping timeout"


def test_build_status_snapshot_uses_readable_mcp_version_fallback_when_configured(tmp_path):
    cfg = AppConfig.default()
    cfg.mcp.executable_path = str(tmp_path / "RenderDocMCP.exe")

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["mcp"]["version"] != "unknown"
    assert snapshot["mcp"]["version"] == "版本未记录"


def test_build_status_snapshot_formats_mcp_setup_asset_name_as_version():
    cfg = AppConfig.default()
    cfg.mcp.asset_name = "RenderDocMCP-Setup-1.0.1.exe"

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["mcp"]["version"] == "v1.0.1"


def test_build_status_snapshot_exposes_distinct_capture_and_export_output_dirs():
    cfg = AppConfig.default()
    cfg.capture.last_output_dir = "D:\\RdcCaptures"
    cfg.export.last_output_dir = "D:\\RdcExports"

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["paths"]["capture_output_dir"] == "D:\\RdcCaptures"
    assert snapshot["paths"]["export_output_dir"] == "D:\\RdcExports"
    assert snapshot["paths"]["last_output_dir"] == "D:\\RdcCaptures"


def test_build_status_snapshot_masks_saved_ai_api_key():
    cfg = AppConfig.default()
    cfg.ai.api_key = "sk-secret"

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["ai"]["api_key_saved"] is True
    assert snapshot["config_preview"]["ai"]["api_key"] == "********"


def test_bridge_get_status_returns_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.get_status({})

    assert response["ok"] is True
    assert "renderdoc" in response["data"]
    assert response["logs"] == []


def test_bridge_keeps_bound_window_private_to_avoid_pywebview_api_recursion():
    bridge = GuiBridge(run_jobs_inline=True)
    window = object()

    bridge.bind_window(window)

    assert "window" not in bridge.__dict__
    assert bridge._window is window


def test_bridge_save_environment_updates_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_environment(
        {
            "renderdoc_path": "C:\\Program Files\\RenderDoc\\qrenderdoc.exe",
            "mcp_path": "C:\\Users\\me\\AppData\\Local\\Programs\\RenderDocMCP\\RenderDocMCP.exe",
            "mumu_root": "D:\\MuMu",
            "vm_index": "1",
            "graphics_api": "vulkan",
        }
    )

    assert response["ok"] is True
    assert response["data"]["mumu"]["vm_index"] == "1"
    assert load_config().mcp.executable_path == "C:\\Users\\me\\AppData\\Local\\Programs\\RenderDocMCP\\RenderDocMCP.exe"


def test_bridge_save_mcp_accepts_extension_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    extension_dir = tmp_path / "renderdoc_mcp_bridge"
    extension_dir.mkdir()
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_mcp({"mcp_path": str(extension_dir)})

    assert response["ok"] is True
    cfg = load_config()
    assert cfg.mcp.extension_dir == str(extension_dir)
    assert cfg.mcp.executable_path == ""


def test_bridge_save_capture_paths_updates_last_rdc_and_output_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)
    rdc_path = tmp_path / "captures" / "manual.rdc"
    output_dir = tmp_path / "exports"

    response = bridge.save_capture_paths({"rdc_path": str(rdc_path), "output_dir": str(output_dir)})

    assert response["ok"] is True
    cfg = load_config()
    assert cfg.capture.last_rdc_path == str(rdc_path)
    assert cfg.capture.last_output_dir == str(output_dir)
    assert response["data"]["paths"]["last_rdc_path"] == str(rdc_path)


def test_bridge_save_capture_paths_keeps_capture_and_export_output_dirs_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_capture_paths(
        {
            "capture_output_dir": "D:\\RdcCaptures",
            "export_output_dir": "D:\\RdcExports",
        }
    )

    assert response["ok"] is True
    cfg = load_config()
    assert cfg.capture.last_output_dir == "D:\\RdcCaptures"
    assert cfg.export.last_output_dir == "D:\\RdcExports"
    assert response["data"]["paths"]["capture_output_dir"] == "D:\\RdcCaptures"
    assert response["data"]["paths"]["export_output_dir"] == "D:\\RdcExports"


def test_bridge_start_job_supports_renderdoc_and_mcp_setup(monkeypatch):
    bridge = GuiBridge(run_jobs_inline=True)
    calls = []

    def fake_setup(ctx):
        calls.append("setup_renderdoc_and_mcp")

    monkeypatch.setattr("rdc_auto.gui.bridge.setup_renderdoc_and_mcp", fake_setup)

    response = bridge.start_job({"action": "setup_renderdoc_mcp"})
    job = bridge.get_job({"job_id": response["data"]["job_id"]})

    assert job["data"]["state"] == "succeeded"
    assert calls == ["setup_renderdoc_and_mcp"]


def test_bridge_save_environment_canonicalizes_nested_mumu_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    mumu_root = tmp_path / "MuMuPlayer"
    mumu_exe = mumu_root / "nx_main" / "MuMuNxMain.exe"
    mumu_exe.parent.mkdir(parents=True)
    mumu_exe.write_bytes(b"exe")
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_environment({"mumu_root": str(mumu_exe.parent)})

    assert response["ok"] is True
    assert response["data"]["mumu"]["root_dir"] == str(mumu_root)
    assert response["data"]["mumu"]["ready"] is True


def test_bridge_save_environment_returns_ready_mumu_status_for_valid_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    mumu_root = tmp_path / "MuMu12"
    mumu_exe = mumu_root / "nx_main" / "MuMuNxMain.exe"
    mumu_exe.parent.mkdir(parents=True)
    mumu_exe.write_bytes(b"exe")
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_environment({"mumu_root": str(mumu_root)})

    assert response["ok"] is True
    assert response["data"]["mumu"]["ready"] is True
    assert response["data"]["mumu"]["invalid_reason"] == ""


def test_bridge_save_ai_does_not_persist_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_ai(
        {
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-secret",
        }
    )

    assert response["ok"] is True
    assert load_config().ai.api_key == ""


def test_bridge_start_job_unsupported_action_returns_error_envelope():
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.start_job({"action": "missing"})

    assert response["ok"] is False
    assert response["error"]["type"] == "ValueError"
    assert response["error"]["action_required"] is False


def test_bridge_job_failure_preserves_user_action_required(monkeypatch):
    bridge = GuiBridge(run_jobs_inline=True)

    def fail(ctx):
        raise UserActionRequired("needs user action")

    monkeypatch.setattr("rdc_auto.gui.bridge.check_environment", fail)
    response = bridge.start_job({"action": "check_environment"})
    job = bridge.get_job({"job_id": response["data"]["job_id"]})

    assert response["ok"] is True
    assert job["ok"] is True
    assert job["data"]["state"] == "failed"
    assert job["data"]["error"]["action_required"] is True


def test_bridge_attach_parses_false_string_params_as_false(monkeypatch):
    bridge = GuiBridge(run_jobs_inline=True)
    calls = []

    def fake_attach(ctx, force, confirm_vulkan, vm_index=""):
        calls.append({"force": force, "confirm_vulkan": confirm_vulkan, "vm_index": vm_index})
        return "launch-1"

    monkeypatch.setattr("rdc_auto.gui.bridge.attach", fake_attach)
    response = bridge.start_job(
        {
            "action": "attach",
            "params": {"force": "false", "confirm_vulkan": "false", "vm_index": "1"},
        }
    )
    job = bridge.get_job({"job_id": response["data"]["job_id"]})

    assert job["data"]["state"] == "succeeded"
    assert calls == [{"force": False, "confirm_vulkan": False, "vm_index": "1"}]


def test_bridge_restart_mcp_forces_release_of_stale_capture_session(monkeypatch):
    bridge = GuiBridge(run_jobs_inline=True)
    calls = []

    def fake_restart(ctx, force_release_session=False):
        calls.append(force_release_session)
        return object()

    monkeypatch.setattr("rdc_auto.gui.bridge.restart_mcp", fake_restart)

    response = bridge.start_job({"action": "restart_mcp"})
    job = bridge.get_job({"job_id": response["data"]["job_id"]})

    assert job["data"]["state"] == "succeeded"
    assert calls == [True]


def test_bridge_shutdown_terminates_only_mcp_pid_started_by_start_action(monkeypatch):
    bridge = GuiBridge(run_jobs_inline=True)
    stage = {"value": "before"}
    pids_by_stage = {
        "before": {"qrenderdoc.exe": set(), "RenderDocMCP.exe": set(), "renderdoc-mcp.exe": set()},
        "after": {"qrenderdoc.exe": {101}, "RenderDocMCP.exe": set(), "renderdoc-mcp.exe": set()},
        "shutdown": {"qrenderdoc.exe": {101, 202}, "RenderDocMCP.exe": set(), "renderdoc-mcp.exe": set()},
    }
    terminated = []

    def fake_process_ids(image_name):
        return pids_by_stage[stage["value"]].get(image_name, set())

    def fake_start(ctx):
        stage["value"] = "after"
        return object()

    monkeypatch.setattr("rdc_auto.gui.bridge.process_ids", fake_process_ids)
    monkeypatch.setattr("rdc_auto.gui.bridge.terminate_process_tree_by_pid", lambda pid: terminated.append(pid))
    monkeypatch.setattr("rdc_auto.gui.bridge.start_mcp", fake_start)
    monkeypatch.setattr("rdc_auto.gui.bridge.release_session", lambda ctx: None)

    response = bridge.start_job({"action": "start_mcp"})
    job = bridge.get_job({"job_id": response["data"]["job_id"]})
    stage["value"] = "shutdown"
    shutdown = bridge.shutdown({})

    assert job["data"]["state"] == "succeeded"
    assert shutdown["ok"] is True
    assert terminated == [101]


def test_bridge_shutdown_does_not_terminate_mcp_pid_reused_by_start_action(monkeypatch):
    bridge = GuiBridge(run_jobs_inline=True)
    pids = {"qrenderdoc.exe": {101}, "RenderDocMCP.exe": set(), "renderdoc-mcp.exe": set()}
    terminated = []

    monkeypatch.setattr("rdc_auto.gui.bridge.process_ids", lambda image_name: pids.get(image_name, set()))
    monkeypatch.setattr("rdc_auto.gui.bridge.terminate_process_tree_by_pid", lambda pid: terminated.append(pid))
    monkeypatch.setattr("rdc_auto.gui.bridge.start_mcp", lambda ctx: object())

    response = bridge.start_job({"action": "start_mcp"})
    job = bridge.get_job({"job_id": response["data"]["job_id"]})
    shutdown = bridge.shutdown({})

    assert job["data"]["state"] == "succeeded"
    assert shutdown["ok"] is True
    assert terminated == []


def test_bridge_shutdown_terminates_mcp_pid_started_by_export_action(monkeypatch, tmp_path):
    bridge = GuiBridge(run_jobs_inline=True)
    stage = {"value": "before"}
    pids_by_stage = {
        "before": {"qrenderdoc.exe": set(), "RenderDocMCP.exe": set(), "renderdoc-mcp.exe": set()},
        "after": {"qrenderdoc.exe": {303}, "RenderDocMCP.exe": set(), "renderdoc-mcp.exe": set()},
        "shutdown": {"qrenderdoc.exe": {303}, "RenderDocMCP.exe": set(), "renderdoc-mcp.exe": set()},
    }
    terminated = []

    def fake_process_ids(image_name):
        return pids_by_stage[stage["value"]].get(image_name, set())

    def fake_export_assets(ctx, rdc_path, output_dir, assets):
        stage["value"] = "after"
        return {"source_rdc": rdc_path, "assets": assets}

    monkeypatch.setattr("rdc_auto.gui.bridge.process_ids", fake_process_ids)
    monkeypatch.setattr("rdc_auto.gui.bridge.terminate_process_tree_by_pid", lambda pid: terminated.append(pid))
    monkeypatch.setattr("rdc_auto.gui.bridge.export_assets", fake_export_assets)
    monkeypatch.setattr("rdc_auto.gui.bridge.release_session", lambda ctx: None)

    response = bridge.start_job(
        {
            "action": "export",
            "params": {
                "rdc_path": str(tmp_path / "capture.rdc"),
                "output_dir": str(tmp_path / "out"),
                "assets": "both",
            },
        }
    )
    job = bridge.get_job({"job_id": response["data"]["job_id"]})
    stage["value"] = "shutdown"
    shutdown = bridge.shutdown({})

    assert job["data"]["state"] == "succeeded"
    assert shutdown["ok"] is True
    assert terminated == [303]


def test_bridge_get_status_returns_error_envelope_on_runtime_error(monkeypatch):
    bridge = GuiBridge(run_jobs_inline=True)

    def fail_load_config():
        raise ValueError("bad config")

    monkeypatch.setattr("rdc_auto.gui.bridge.load_config", fail_load_config)
    response = bridge.get_status({})

    assert response["ok"] is False
    assert response["error"]["type"] == "ValueError"
    assert response["error"]["message"] == "bad config"


def test_bridge_open_path_empty_payload_returns_error_without_opening(monkeypatch):
    bridge = GuiBridge(run_jobs_inline=True)
    opened = []

    monkeypatch.setattr("rdc_auto.gui.bridge.os.startfile", lambda path: opened.append(path), raising=False)
    response = bridge.open_path({})

    assert response["ok"] is False
    assert opened == []


def test_bridge_load_eid_list_returns_rows(monkeypatch, tmp_path):
    class FakeExportService:
        def __init__(self, mcp):
            self.mcp = mcp

        def list_draw_calls(self, rdc_path):
            assert self.mcp == "mcp"
            assert rdc_path == str(tmp_path / "capture.rdc")
            return [{"event_id": 1203, "name": "Character.Draw"}]

    monkeypatch.setattr("rdc_auto.gui.bridge.load_config", lambda: "cfg")
    monkeypatch.setattr("rdc_auto.gui.bridge.mcp_client", lambda cfg: "mcp")
    monkeypatch.setattr("rdc_auto.gui.bridge.ExportService", FakeExportService)
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.load_eid_list({"rdc_path": str(tmp_path / "capture.rdc")})

    assert response["ok"] is True
    assert response["data"] == {"rows": [{"event_id": 1203, "name": "Character.Draw"}]}
    assert response["logs"] == ["loaded 1 EID rows"]


def test_bridge_export_eid_model_returns_error_for_invalid_event_id(tmp_path):
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.export_eid_model(
        {"rdc_path": str(tmp_path / "capture.rdc"), "output_dir": str(tmp_path / "out"), "event_id": "abc"}
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "ValueError"


@pytest.mark.parametrize("event_id", [True, 12.7, "0"])
def test_bridge_export_eid_model_rejects_non_strict_event_ids_before_mcp(monkeypatch, tmp_path, event_id):
    def fail_mcp_client(cfg):
        raise AssertionError("mcp_client should not be called for invalid event_id")

    monkeypatch.setattr("rdc_auto.gui.bridge.load_config", lambda: "cfg")
    monkeypatch.setattr("rdc_auto.gui.bridge.mcp_client", fail_mcp_client)
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.export_eid_model(
        {"rdc_path": str(tmp_path / "capture.rdc"), "output_dir": str(tmp_path / "out"), "event_id": event_id}
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "ValueError"
    assert response["error"]["message"].startswith("invalid event_id:")


def test_bridge_export_eid_textures_returns_result(monkeypatch, tmp_path):
    class FakeExportService:
        def __init__(self, mcp):
            self.mcp = mcp

        def export_bound_textures_for_event(self, rdc_path, output_dir, event_id):
            assert self.mcp == "mcp"
            assert rdc_path == str(tmp_path / "capture.rdc")
            assert output_dir == str(tmp_path / "out")
            assert event_id == 1203
            return {"event_id": 1203, "textures": [{"path": str(tmp_path / "out" / "a.png")}]}

    monkeypatch.setattr("rdc_auto.gui.bridge.load_config", lambda: "cfg")
    monkeypatch.setattr("rdc_auto.gui.bridge.mcp_client", lambda cfg: "mcp")
    monkeypatch.setattr("rdc_auto.gui.bridge.ExportService", FakeExportService)
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.export_eid_textures(
        {"rdc_path": str(tmp_path / "capture.rdc"), "output_dir": str(tmp_path / "out"), "event_id": "1203"}
    )

    assert response["ok"] is True
    assert response["data"] == {"event_id": 1203, "textures": [{"path": str(tmp_path / "out" / "a.png")}]}
    assert response["logs"] == ["exported 1 textures for EID 1203"]


@pytest.mark.parametrize("event_id", [False, 4.2, 0])
def test_bridge_export_eid_textures_rejects_non_strict_event_ids_before_mcp(monkeypatch, tmp_path, event_id):
    def fail_mcp_client(cfg):
        raise AssertionError("mcp_client should not be called for invalid event_id")

    monkeypatch.setattr("rdc_auto.gui.bridge.load_config", lambda: "cfg")
    monkeypatch.setattr("rdc_auto.gui.bridge.mcp_client", fail_mcp_client)
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.export_eid_textures(
        {"rdc_path": str(tmp_path / "capture.rdc"), "output_dir": str(tmp_path / "out"), "event_id": event_id}
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "ValueError"
    assert response["error"]["message"].startswith("invalid event_id:")


def test_bridge_export_eid_textures_returns_clear_unsupported_capability_error(monkeypatch, tmp_path):
    class FakeExportService:
        def __init__(self, mcp):
            self.mcp = mcp

        def export_bound_textures_for_event(self, rdc_path, output_dir, event_id):
            raise McpCapabilityMissing("Installed RenderDocMCP does not support EID bound texture export.")

    monkeypatch.setattr("rdc_auto.gui.bridge.load_config", lambda: "cfg")
    monkeypatch.setattr("rdc_auto.gui.bridge.mcp_client", lambda cfg: "mcp")
    monkeypatch.setattr("rdc_auto.gui.bridge.ExportService", FakeExportService)
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.export_eid_textures(
        {"rdc_path": str(tmp_path / "capture.rdc"), "output_dir": str(tmp_path / "out"), "event_id": "1203"}
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "McpCapabilityMissing"
    assert response["error"]["message"] == "Installed RenderDocMCP does not support EID bound texture export."


def test_bridge_list_rdc_files_returns_directory_files_newest_first(tmp_path):
    old = tmp_path / "old.rdc"
    recent = tmp_path / "recent.rdc"
    ignored = tmp_path / "notes.txt"
    old.write_text("old", encoding="utf-8")
    recent.write_text("recent", encoding="utf-8")
    ignored.write_text("ignored", encoding="utf-8")
    os.utime(old, (100, 100))
    os.utime(recent, (200, 200))

    bridge = GuiBridge(run_jobs_inline=True)
    response = bridge.list_rdc_files({"directory": str(tmp_path)})

    assert response["ok"] is True
    assert response["data"] == {"files": [str(recent), str(old)]}
    assert response["logs"] == ["found 2 RDC files"]


class FakeWindow:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.calls.append((dialog_type, kwargs))
        return self.result


def test_choose_directory_uses_window_dialog(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(FOLDER_DIALOG="folder", OPEN_DIALOG="open"),
    )
    bridge = GuiBridge(run_jobs_inline=True)
    bridge.bind_window(FakeWindow([str(tmp_path)]))

    response = bridge.choose_directory({"initial_dir": str(tmp_path)})

    assert response["ok"] is True
    assert response["data"]["path"] == str(tmp_path)
