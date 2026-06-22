from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from copy import deepcopy


JobCallable = Callable[[Callable[[str, int], None]], dict]


class JobManager:
    def __init__(self, run_inline: bool = False):
        self.run_inline = run_inline
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def start(self, action: str, fn: JobCallable) -> dict:
        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "action": action,
            "state": "queued",
            "progress": 0,
            "logs": [],
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            self._jobs[job_id] = job
            initial = self._snapshot(job)
        if self.run_inline:
            self._run(job_id, fn)
        else:
            thread = threading.Thread(target=self._run, args=(job_id, fn), daemon=True)
            thread.start()
        return initial

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                now = time.time()
                return {
                    "job_id": job_id,
                    "action": "",
                    "state": "missing",
                    "progress": 0,
                    "logs": [],
                    "result": None,
                    "error": {"type": "JobMissing", "message": f"Unknown job: {job_id}"},
                    "created_at": now,
                    "updated_at": now,
                }
            return self._snapshot(job)

    def _run(self, job_id: str, fn: JobCallable) -> None:
        self._update(job_id, state="running", progress=1)

        def emit(message: str, progress: int) -> None:
            with self._lock:
                job = self._jobs[job_id]
                job["logs"].append(message)
                job["progress"] = max(job["progress"], min(99, int(progress)))
                job["updated_at"] = time.time()

        try:
            result = fn(emit)
        except Exception as exc:
            self._update(
                job_id,
                state="failed",
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "action_required": type(exc).__name__ == "UserActionRequired",
                },
            )
            return
        self._update(job_id, state="succeeded", progress=100, result=result)

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(changes)
            job["updated_at"] = time.time()

    def _snapshot(self, job: dict) -> dict:
        return {
            **job,
            "logs": list(job["logs"]),
            "result": deepcopy(job["result"]),
            "error": deepcopy(job["error"]),
        }
