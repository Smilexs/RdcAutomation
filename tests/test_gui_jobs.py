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
