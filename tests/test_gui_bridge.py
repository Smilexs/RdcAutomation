from __future__ import annotations

from rdc_auto.config import AppConfig, load_config
from rdc_auto.errors import UserActionRequired
from rdc_auto.gui.bridge import GuiBridge
from rdc_auto.gui.status import build_status_snapshot


def test_build_status_snapshot_contains_topbar_sections(tmp_path):
    cfg = AppConfig.default()
    cfg.renderdoc.qrenderdoc_path = str(tmp_path / "qrenderdoc.exe")
    cfg.mcp.executable_path = str(tmp_path / "RenderDocMCP.exe")
    cfg.emulator.root_dir = str(tmp_path / "MuMu")
    cfg.capture.active_launch_id = "launch-1"

    snapshot = build_status_snapshot(cfg, process_counts={"qrenderdoc.exe": 1})

    assert snapshot["renderdoc"]["path"].endswith("qrenderdoc.exe")
    assert snapshot["mcp"]["running"] is True
    assert snapshot["session"]["attached"] is True
    assert snapshot["session"]["launch_id"] == "launch-1"
    assert snapshot["config_preview"]["capture"]["active_launch_id"] == "launch-1"


def test_build_status_snapshot_empty_process_counts_are_authoritative(monkeypatch):
    cfg = AppConfig.default()

    def fail_count_processes(name: str) -> int:
        raise AssertionError(f"unexpected live process probe for {name}")

    monkeypatch.setattr("rdc_auto.gui.status.count_processes", fail_count_processes)

    snapshot = build_status_snapshot(cfg, process_counts={})

    assert snapshot["mcp"]["running"] is False
    assert snapshot["mcp"]["extension_loaded"] is False


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


def test_bridge_save_environment_updates_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    bridge = GuiBridge(run_jobs_inline=True)

    response = bridge.save_environment(
        {
            "renderdoc_path": "C:\\Program Files\\RenderDoc\\qrenderdoc.exe",
            "mumu_root": "D:\\MuMu",
            "vm_index": "1",
            "graphics_api": "vulkan",
        }
    )

    assert response["ok"] is True
    assert response["data"]["mumu"]["vm_index"] == "1"


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
