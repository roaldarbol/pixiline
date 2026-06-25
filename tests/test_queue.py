"""Tests for the JobQueue state machine.

The real Worker spawns ``pixi run`` subprocesses, so it is swapped for a fake that
records ``start``/``cancel`` and lets a test drive the finished/failed/canceled
signals by hand. That isolates the queue's bookkeeping (staging, the worker-slot
limit, removal/cancellation) from any real process.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from pixiline.jobs import queue as queue_mod
from pixiline.jobs.job import Job, JobState
from pixiline.jobs.queue import JobQueue, suggested_worker_count


class FakeWorker(QObject):
    progress = Signal(int, float)
    step_changed = Signal(int, int, str)
    log = Signal(int, str)
    finished = Signal(int)
    failed = Signal(int, str)
    canceled = Signal(int)

    instances: list[FakeWorker] = []

    def __init__(self, job: Job, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.job = job
        self.started = False
        self.cancel_called = False
        FakeWorker.instances.append(self)

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancel_called = True


@pytest.fixture(autouse=True)
def fake_worker(monkeypatch):
    FakeWorker.instances.clear()
    monkeypatch.setattr(queue_mod, "Worker", FakeWorker)
    yield FakeWorker


@pytest.fixture
def make_job(sample_pipeline):
    def _make(name: str = "clip") -> Job:
        return Job(
            pipeline=sample_pipeline,
            input_path=Path(f"/data/{name}.mp4"),
            output_base=Path("/out"),
            steps=["motion", "track"],
        )

    return _make


def collect(signal) -> list:
    """Attach a collector to a single-arg signal and return the backing list."""
    seen: list = []
    signal.connect(seen.append)
    return seen


# --- suggested_worker_count / construction ----------------------------------


def test_suggested_worker_count_in_bounds():
    assert 1 <= suggested_worker_count() <= 3


def test_constructor_rejects_zero_workers(qapp):
    with pytest.raises(ValueError, match=">= 1"):
        JobQueue(max_workers=0)


def test_set_max_workers_rejects_zero(qapp):
    q = JobQueue()
    with pytest.raises(ValueError, match=">= 1"):
        q.set_max_workers(0)


# --- submit / staging -------------------------------------------------------


def test_submit_stages_without_running(qapp, make_job):
    q = JobQueue()
    added = collect(q.job_added)
    job_id = q.submit(make_job())
    assert q.get(job_id).state is JobState.QUEUED
    assert added == [job_id]
    assert q.has_staged() is True
    assert q.is_idle() is True
    assert FakeWorker.instances == []  # nothing started


def test_submit_duplicate_raises(qapp, make_job):
    q = JobQueue()
    job = make_job()
    q.submit(job)
    with pytest.raises(ValueError, match="already enqueued"):
        q.submit(job)


def test_get_unknown_returns_none(qapp):
    assert JobQueue().get(999) is None


# --- start / worker-slot limit ----------------------------------------------


def test_start_releases_and_runs(qapp, make_job):
    q = JobQueue()
    pending = collect(q.job_pending)
    started = collect(q.job_started)
    job_id = q.submit(make_job())
    q.start([job_id])
    assert pending == [job_id]
    assert started == [job_id]
    assert len(FakeWorker.instances) == 1
    assert FakeWorker.instances[0].started is True
    assert q.is_idle() is False
    assert q.has_staged() is False


def test_start_only_affects_queued_jobs(qapp, make_job):
    q = JobQueue()
    job_id = q.submit(make_job())
    q.start([job_id])
    q.start([job_id])  # already running -> ignored, no second worker
    assert len(FakeWorker.instances) == 1


def test_max_workers_limit_then_next_starts_on_finish(qapp, make_job):
    q = JobQueue(max_workers=1)
    a = q.submit(make_job("a"))
    b = q.submit(make_job("b"))
    finished = collect(q.job_finished)
    q.start_all()
    assert len(FakeWorker.instances) == 1  # only one slot
    # Finish the first; the second should now start.
    FakeWorker.instances[0].finished.emit(a)
    assert finished == [a]
    assert len(FakeWorker.instances) == 2
    assert FakeWorker.instances[1].job.id == b


def test_raising_max_workers_starts_more(qapp, make_job):
    q = JobQueue(max_workers=1)
    q.submit(make_job("a"))
    q.submit(make_job("b"))
    q.start_all()
    assert len(FakeWorker.instances) == 1
    q.set_max_workers(2)
    assert len(FakeWorker.instances) == 2


# --- remove -----------------------------------------------------------------


def test_remove_staged_job(qapp, make_job):
    q = JobQueue()
    removed = collect(q.job_removed)
    job_id = q.submit(make_job())
    assert q.remove(job_id) is True
    assert q.get(job_id) is None
    assert removed == [job_id]


def test_remove_active_job_refused(qapp, make_job):
    q = JobQueue()
    job_id = q.submit(make_job())
    q.start([job_id])
    assert q.remove(job_id) is False
    assert q.get(job_id) is not None


def test_remove_pending_job(qapp, make_job):
    q = JobQueue(max_workers=1)
    q.submit(make_job("a"))
    b = q.submit(make_job("b"))
    q.start_all()  # a active, b waits as PENDING
    assert q.remove(b) is True
    assert q.get(b) is None


def test_jobs_lists_every_submitted_job(qapp, make_job):
    q = JobQueue()
    ids = {q.submit(make_job("a")), q.submit(make_job("b"))}
    assert {j.id for j in q.jobs()} == ids


# --- cancel -----------------------------------------------------------------


def test_cancel_staged_job(qapp, make_job):
    q = JobQueue()
    canceled = collect(q.job_canceled)
    job_id = q.submit(make_job())
    q.cancel(job_id)
    assert q.get(job_id).state is JobState.CANCELED
    assert canceled == [job_id]


def test_cancel_pending_job(qapp, make_job):
    q = JobQueue(max_workers=1)
    q.submit(make_job("a"))
    b = q.submit(make_job("b"))
    q.start_all()  # a runs, b waits as PENDING
    q.cancel(b)
    assert q.get(b).state is JobState.CANCELED


def test_cancel_active_delegates_to_worker(qapp, make_job):
    q = JobQueue()
    job_id = q.submit(make_job())
    q.start([job_id])
    q.cancel(job_id)
    assert FakeWorker.instances[0].cancel_called is True


def test_cancel_unknown_is_noop(qapp):
    JobQueue().cancel(999)  # must not raise


# --- worker outcomes --------------------------------------------------------


def test_failed_worker_frees_slot(qapp, make_job):
    q = JobQueue()
    failed: list[tuple[int, str]] = []
    q.job_failed.connect(lambda jid, msg: failed.append((jid, msg)))
    job_id = q.submit(make_job())
    q.start([job_id])
    FakeWorker.instances[0].failed.emit(job_id, "boom")
    assert failed == [(job_id, "boom")]
    assert q.is_idle() is True


def test_canceled_worker_frees_slot(qapp, make_job):
    q = JobQueue()
    canceled = collect(q.job_canceled)
    job_id = q.submit(make_job())
    q.start([job_id])
    FakeWorker.instances[0].canceled.emit(job_id)
    assert canceled == [job_id]
    assert q.is_idle() is True


# --- shutdown ---------------------------------------------------------------


def test_shutdown_clears_pending_and_cancels_active(qapp, make_job):
    q = JobQueue(max_workers=1)
    q.submit(make_job("a"))
    q.submit(make_job("b"))
    q.start_all()  # a active, b pending
    q.shutdown()
    assert FakeWorker.instances[0].cancel_called is True
    # Finishing the canceled active job must not start the dropped pending one.
    FakeWorker.instances[0].canceled.emit(FakeWorker.instances[0].job.id)
    assert len(FakeWorker.instances) == 1
