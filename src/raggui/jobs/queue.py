"""Job queue. Stages jobs, then runs up to ``max_workers`` of them concurrently.

Mirrors croppy's queue: submitting stages a job (QUEUED) without running it; jobs
run only once released via :meth:`start` / :meth:`start_all`. Default is one job
at a time — the GPU steps (motion/predict) would contend if run in parallel — but
``max_workers`` can be raised for machines that can take it.
"""

from __future__ import annotations

import os
from collections import deque

from PySide6.QtCore import QObject, Signal

from raggui.jobs.job import Job, JobState
from raggui.jobs.worker import Worker

DEFAULT_MAX_WORKERS = 1


def suggested_worker_count() -> int:
    """A conservative parallel-job count. The heavy steps are GPU/IO bound, so we
    stay low; the user opts in via the Jobs-tab toggle. Always at least 1."""
    cores = os.cpu_count() or 1
    return max(1, min(3, cores // 4))


class JobQueue(QObject):
    job_added = Signal(int)
    job_pending = Signal(int)
    job_started = Signal(int)
    job_progress = Signal(int, float)  # job_id, fraction
    job_step = Signal(int, int, str)  # job_id, step_index, step_name
    job_log = Signal(int, str)  # job_id, text
    job_finished = Signal(int)
    job_failed = Signal(int, str)
    job_canceled = Signal(int)
    job_removed = Signal(int)

    def __init__(
        self, max_workers: int = DEFAULT_MAX_WORKERS, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self._max_workers = max_workers
        self._pending: deque[Job] = deque()
        self._active: dict[int, Worker] = {}
        self._jobs: dict[int, Job] = {}

    # --- public API ---------------------------------------------------------

    def submit(self, job: Job) -> int:
        if job.id in self._jobs:
            raise ValueError(f"Job {job.id} is already enqueued")
        job.state = JobState.QUEUED
        self._jobs[job.id] = job
        self.job_added.emit(job.id)
        return job.id

    def start(self, job_ids: list[int]) -> None:
        for job_id in job_ids:
            job = self._jobs.get(job_id)
            if job is not None and job.state == JobState.QUEUED:
                job.state = JobState.PENDING
                self._pending.append(job)
                self.job_pending.emit(job.id)
        self._maybe_start_next()

    def start_all(self) -> None:
        self.start([j.id for j in self._jobs.values() if j.state == JobState.QUEUED])

    def remove(self, job_id: int) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.id in self._active:
            return False
        if job in self._pending:
            self._pending.remove(job)
        del self._jobs[job_id]
        self.job_removed.emit(job_id)
        return True

    def cancel(self, job_id: int) -> None:
        worker = self._active.get(job_id)
        if worker is not None:
            worker.cancel()
            return
        job = self._jobs.get(job_id)
        if job is None:
            return
        if job in self._pending:
            self._pending.remove(job)
        if job.state in (JobState.QUEUED, JobState.PENDING):
            job.state = JobState.CANCELED
            self.job_canceled.emit(job_id)

    def set_max_workers(self, n: int) -> None:
        if n < 1:
            raise ValueError("max_workers must be >= 1")
        self._max_workers = n
        self._maybe_start_next()

    def shutdown(self) -> None:
        """Drop pending jobs and cancel running ones so no pixi/processing
        subprocesses are orphaned when the app exits."""
        self._pending.clear()
        for worker in list(self._active.values()):
            worker.cancel()

    def jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def get(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    def has_staged(self) -> bool:
        return any(j.state == JobState.QUEUED for j in self._jobs.values())

    def is_idle(self) -> bool:
        return not self._active and not self._pending

    # --- internals ----------------------------------------------------------

    def _maybe_start_next(self) -> None:
        while self._pending and len(self._active) < self._max_workers:
            job = self._pending.popleft()
            worker = Worker(job, parent=self)
            worker.progress.connect(self.job_progress)
            worker.step_changed.connect(self.job_step)
            worker.log.connect(self.job_log)
            worker.finished.connect(self._on_worker_finished)
            worker.failed.connect(self._on_worker_failed)
            worker.canceled.connect(self._on_worker_canceled)
            self._active[job.id] = worker
            self.job_started.emit(job.id)
            worker.start()

    def _on_worker_finished(self, job_id: int) -> None:
        self._active.pop(job_id, None)
        self.job_finished.emit(job_id)
        self._maybe_start_next()

    def _on_worker_failed(self, job_id: int, message: str) -> None:
        self._active.pop(job_id, None)
        self.job_failed.emit(job_id, message)
        self._maybe_start_next()

    def _on_worker_canceled(self, job_id: int) -> None:
        self._active.pop(job_id, None)
        self.job_canceled.emit(job_id)
        self._maybe_start_next()
