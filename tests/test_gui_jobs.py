from __future__ import annotations

import json
import threading
import time

from rdc_auto.errors import UserActionRequired
from rdc_auto.gui.jobs import JobManager


def _wait_for_state(manager: JobManager, job_id: str, state: str) -> dict:
    for _ in range(100):
        current = manager.get(job_id)
        if current["state"] == state:
            return current
        time.sleep(0.01)
    return manager.get(job_id)


def test_job_manager_records_success():
    manager = JobManager(run_inline=True)

    job = manager.start("sample", lambda emit: {"value": 7})

    assert job["state"] == "queued"
    current = manager.get(job["job_id"])
    assert current["state"] == "succeeded"
    assert current["result"] == {"value": 7}
    assert current["progress"] == 100


def test_job_manager_records_failure():
    manager = JobManager(run_inline=True)

    def fail(emit):
        emit("starting", 10)
        raise ValueError("bad input")

    job = manager.start("sample", fail)
    current = manager.get(job["job_id"])

    assert current["state"] == "failed"
    assert current["error"]["type"] == "ValueError"
    assert current["error"]["message"] == "bad input"
    assert current["logs"] == ["starting"]


def test_job_manager_missing_job_includes_timestamps():
    manager = JobManager(run_inline=True)

    current = manager.get("unknown")

    assert current["state"] == "missing"
    assert isinstance(current["created_at"], float)
    assert isinstance(current["updated_at"], float)


def test_job_manager_start_returns_detached_queued_snapshot():
    manager = JobManager(run_inline=True)

    def run(emit):
        emit("starting", 10)
        return {"value": 7}

    job = manager.start("sample", run)
    current = manager.get(job["job_id"])

    assert job["state"] == "queued"
    assert job["logs"] == []
    assert current["state"] == "succeeded"
    assert current["logs"] == ["starting"]


def test_job_manager_records_are_json_serializable():
    manager = JobManager(run_inline=True)

    success = manager.start("success", lambda emit: {"value": 7})

    def fail(emit):
        raise ValueError("bad input")

    failure = manager.start("failure", fail)

    json.dumps(manager.get(success["job_id"]))
    json.dumps(manager.get(failure["job_id"]))
    json.dumps(manager.get("missing"))


def test_job_manager_fails_non_json_serializable_result():
    manager = JobManager(run_inline=True)

    job = manager.start("sample", lambda emit: {"value": object()})
    current = manager.get(job["job_id"])

    assert current["state"] == "failed"
    assert current["result"] is None
    assert current["error"]["type"] == "TypeError"
    json.dumps(current)


def test_job_manager_threaded_run_reports_running_then_succeeded():
    manager = JobManager(run_inline=False)
    emitted = threading.Event()
    release = threading.Event()

    def run(emit):
        emit("halfway", 40)
        emitted.set()
        release.wait(timeout=1)
        return {"value": 7}

    job = manager.start("sample", run)

    assert emitted.wait(timeout=1)
    current = manager.get(job["job_id"])
    assert current["state"] == "running"
    assert current["progress"] == 40
    assert current["logs"] == ["halfway"]

    release.set()
    current = _wait_for_state(manager, job["job_id"], "succeeded")

    assert current["state"] == "succeeded"
    assert current["progress"] == 100
    assert current["result"] == {"value": 7}


def test_job_manager_caps_emitted_progress_until_success():
    manager = JobManager(run_inline=False)
    emitted = threading.Event()
    release = threading.Event()

    def run(emit):
        emit("almost", 120)
        emitted.set()
        release.wait(timeout=1)
        return {"value": 7}

    job = manager.start("sample", run)

    assert emitted.wait(timeout=1)
    current = manager.get(job["job_id"])
    assert current["state"] == "running"
    assert current["progress"] == 99

    release.set()
    current = _wait_for_state(manager, job["job_id"], "succeeded")

    assert current["progress"] == 100


def test_job_manager_snapshot_mutation_isolated_for_result():
    manager = JobManager(run_inline=True)

    job = manager.start("sample", lambda emit: {"values": []})
    current = manager.get(job["job_id"])
    current["result"]["values"].append("mutated")

    assert manager.get(job["job_id"])["result"] == {"values": []}


def test_job_manager_marks_user_action_required_subclasses():
    class CustomUserActionRequired(UserActionRequired):
        pass

    manager = JobManager(run_inline=True)

    def fail(emit):
        raise CustomUserActionRequired("needs input")

    job = manager.start("sample", fail)
    current = manager.get(job["job_id"])

    assert current["state"] == "failed"
    assert current["error"]["action_required"] is True


def test_job_manager_missing_job_error_has_action_required_false():
    manager = JobManager(run_inline=True)

    current = manager.get("missing")

    assert current["error"]["action_required"] is False
