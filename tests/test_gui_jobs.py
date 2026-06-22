from __future__ import annotations

from rdc_auto.gui.jobs import JobManager


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
