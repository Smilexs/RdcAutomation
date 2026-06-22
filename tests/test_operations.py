from __future__ import annotations

from pathlib import Path

from rdc_auto.config import AppConfig
from rdc_auto.operations import OperationContext, release_session


def test_release_session_clears_capture_state(tmp_path):
    cfg = AppConfig.default()
    cfg.capture.active_session_id = "session-1"
    cfg.capture.active_launch_id = "launch-1"
    cfg.capture.active_pid = 123
    cfg.capture.active_session_started_at = "2026-06-22T00:00:00+08:00"

    release_session(OperationContext(config=cfg))

    assert cfg.capture.active_session_id is None
    assert cfg.capture.active_launch_id == ""
    assert cfg.capture.active_pid is None
    assert cfg.capture.active_session_started_at is None


def test_operation_context_uses_existing_config():
    cfg = AppConfig.default()
    ctx = OperationContext(config=cfg)

    assert ctx.config is cfg
    assert Path(ctx.config.mcp.install_dir).name == "mcp"
