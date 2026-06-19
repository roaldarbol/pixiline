"""Job model: one recording run through its selected pipeline steps.

A job here is a *chain* of steps — each its own ``pixi run`` process — executed in
order by the Worker. The job snapshots everything the Worker needs: the input file,
the ordered step list, the output base, and the overwrite flag.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from raggui.pipeline import ordered

_LOG_CHAR_CAP = 200_000  # keep the in-memory per-job log bounded


class JobState(StrEnum):
    QUEUED = "queued"      # staged, not yet released to run
    PENDING = "pending"    # released, waiting for a free worker slot
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


_job_id_counter = itertools.count(1)


def _next_job_id() -> int:
    return next(_job_id_counter)


@dataclass
class Job:
    """One recording and the steps to run for it."""

    input_path: Path
    steps: list[str]                 # step names, canonical order
    output_base: Path
    overwrite: bool = False
    id: int = field(default_factory=_next_job_id)
    state: JobState = JobState.QUEUED
    current_step: int = 0            # index into steps of the step now running / next
    log: str = ""
    error: str = ""

    def __post_init__(self) -> None:
        # Defensive: always keep steps in canonical order regardless of caller.
        self.steps = ordered(set(self.steps))

    @property
    def stem(self) -> str:
        return self.input_path.stem

    @property
    def label(self) -> str:
        return self.input_path.name

    def current_step_name(self) -> str | None:
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def fraction(self) -> float:
        """Progress in ``[0, 1]`` measured in completed steps."""
        if not self.steps:
            return 0.0
        return max(0.0, min(1.0, self.current_step / len(self.steps)))

    def append_log(self, text: str) -> None:
        self.log += text
        if len(self.log) > _LOG_CHAR_CAP:
            self.log = self.log[-_LOG_CHAR_CAP:]
