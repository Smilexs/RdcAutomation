from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from rdc_auto.errors import McpCapabilityMissing
from rdc_auto.mcp_client import FileIpcMcpClient


def test_file_ipc_client_writes_request_and_reads_response(tmp_path):
    ipc = tmp_path / "renderdoc_mcp"
    client = FileIpcMcpClient(ipc_dir=ipc, poll_interval=0.01, timeout=1.0)

    def responder():
        request_path = ipc / "request.json"
        response_path = ipc / "response.json"
        while not request_path.exists():
            time.sleep(0.01)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request_path.unlink()
        response_path.write_text(json.dumps({"id": request["id"], "result": {"status": "ok"}}), encoding="utf-8")

    thread = threading.Thread(target=responder)
    thread.start()
    result = client.call("ping")
    thread.join(timeout=1)

    assert result == {"status": "ok"}


def test_file_ipc_client_raises_for_missing_method(tmp_path):
    ipc = tmp_path / "renderdoc_mcp"
    client = FileIpcMcpClient(ipc_dir=ipc, poll_interval=0.01, timeout=1.0)

    def responder():
        request_path = ipc / "request.json"
        response_path = ipc / "response.json"
        while not request_path.exists():
            time.sleep(0.01)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request_path.unlink()
        response_path.write_text(
            json.dumps({"id": request["id"], "error": {"code": -32601, "message": "Method not found: launch_application"}}),
            encoding="utf-8",
        )

    thread = threading.Thread(target=responder)
    thread.start()
    with pytest.raises(McpCapabilityMissing):
        client.call("launch_application")
    thread.join(timeout=1)


def test_file_ipc_client_raises_for_method_not_found_code(tmp_path):
    ipc = tmp_path / "renderdoc_mcp"
    client = FileIpcMcpClient(ipc_dir=ipc, poll_interval=0.01, timeout=1.0)

    def responder():
        request_path = ipc / "request.json"
        response_path = ipc / "response.json"
        while not request_path.exists():
            time.sleep(0.01)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request_path.unlink()
        response_path.write_text(
            json.dumps({"id": request["id"], "error": {"code": -32601, "message": "no such tool"}}),
            encoding="utf-8",
        )

    thread = threading.Thread(target=responder)
    thread.start()
    with pytest.raises(McpCapabilityMissing):
        client.call("launch_application")
    thread.join(timeout=1)


def test_file_ipc_client_ignores_stale_response_id(tmp_path):
    ipc = tmp_path / "renderdoc_mcp"
    client = FileIpcMcpClient(ipc_dir=ipc, poll_interval=0.01, timeout=1.0)

    def responder():
        request_path = ipc / "request.json"
        response_path = ipc / "response.json"
        while not request_path.exists():
            time.sleep(0.01)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request_path.unlink()
        response_path.write_text(json.dumps({"id": "stale", "result": {"status": "old"}}), encoding="utf-8")
        time.sleep(0.05)
        response_path.write_text(json.dumps({"id": request["id"], "result": {"status": "ok"}}), encoding="utf-8")

    thread = threading.Thread(target=responder)
    thread.start()
    result = client.call("ping")
    thread.join(timeout=1)

    assert result == {"status": "ok"}


def test_client_starts_installed_executable_once(tmp_path):
    exe = tmp_path / "RenderDocMCP.exe"
    exe.write_bytes(b"exe")
    starts = []

    def popen(args, **kwargs):
        starts.append(args)
        return subprocess.CompletedProcess(args, 0)

    client = FileIpcMcpClient(ipc_dir=tmp_path / "renderdoc_mcp", executable_path=exe, popen=popen)

    client.ensure_started()
    client.ensure_started()

    assert starts == [[str(exe)]]
