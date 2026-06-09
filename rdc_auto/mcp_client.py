from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .errors import McpCapabilityMissing, RdcAutoError


class FileIpcMcpClient:
    def __init__(
        self,
        ipc_dir: Path | None = None,
        executable_path: str | Path | None = None,
        popen=subprocess.Popen,
        poll_interval: float = 0.05,
        timeout: float = 30.0,
    ):
        temp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or Path.home())
        self.ipc_dir = ipc_dir or temp / "renderdoc_mcp"
        self.executable_path = Path(executable_path) if executable_path else None
        self.popen = popen
        self._process = None
        self.poll_interval = poll_interval
        self.timeout = timeout

    def ensure_started(self) -> None:
        if self._process is not None:
            returncode = self._process_returncode(self._process)
            if returncode is None:
                return
            self._process = None
        if self.executable_path is None:
            return
        if not self.executable_path.is_file():
            raise FileNotFoundError(f"RenderDocMCP executable not found: {self.executable_path}")
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self._process = self.popen([str(self.executable_path)], **kwargs)
        returncode = self._process_returncode(self._process)
        if returncode is not None:
            self._process = None
            raise RdcAutoError(f"RenderDocMCP process exited immediately with code {returncode}")

    @staticmethod
    def _process_returncode(process) -> int | None:
        poll = getattr(process, "poll", None)
        if poll is None:
            return None
        return poll()

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        self.ensure_started()
        self.ipc_dir.mkdir(parents=True, exist_ok=True)
        request_id = str(uuid.uuid4())
        request_path = self.ipc_dir / "request.json"
        response_path = self.ipc_dir / "response.json"
        lock_path = self.ipc_dir / "lock"

        if response_path.exists():
            response_path.unlink()

        lock_path.write_text(request_id, encoding="utf-8")
        request_path.write_text(
            json.dumps({"id": request_id, "method": method, "params": params or {}}),
            encoding="utf-8",
        )
        lock_path.unlink(missing_ok=True)

        deadline = time.time() + (timeout if timeout is not None else self.timeout)
        while time.time() < deadline:
            if response_path.exists():
                raw = json.loads(response_path.read_text(encoding="utf-8"))
                response_path.unlink(missing_ok=True)
                if raw.get("id") != request_id:
                    continue
                if "error" in raw:
                    error = raw["error"]
                    message = error.get("message", str(error))
                    if error.get("code") == -32601 or "Method not found" in message:
                        raise McpCapabilityMissing(message)
                    raise RdcAutoError(message)
                result = raw.get("result")
                return result if isinstance(result, dict) else {"value": result}
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Timed out waiting for RenderDocMCP method {method}")

    def ping(self) -> bool:
        return self.call("ping", timeout=3.0).get("status") == "ok"
