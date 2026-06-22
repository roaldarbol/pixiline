"""Job model: one input run through a pipeline's selected steps.

A job is a *chain* of steps - each its own ``pixi run`` process, executed in
dependency order by the Worker. It snapshots everything the Worker needs: the
pipeline (its steps + how to build commands), the input file, the output base,
the ordered step list, and the tunable setting values shared across the run.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from raggui.manifest import Pipeline

_LOG_CHAR_CAP = 200_000  # keep the in-memory per-job log bounded


class JobState(StrEnum):
    QUEUED = "queued"  # staged, not yet released to run
    PENDING = "pending"  # released, waiting for a free worker slot
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


_job_id_counter = itertools.count(1)


def _next_job_id() -> int:
    return next(_job_id_counter)


@dataclass
class Job:
    """One input and the pipeline steps to run for it."""

    pipeline: Pipeline
    input_path: Path
    output_base: Path
    steps: list[str]  # step names
    settings: dict[str, str] = field(default_factory=dict)  # pipeline-level tunables
    id: int = field(default_factory=_next_job_id)
    state: JobState = JobState.QUEUED
    current_step: int = 0  # index into steps of the step now running / next
    log: str = ""
    error: str = ""

    def __post_init__(self) -> None:
        # Keep steps in dependency (topological) order regardless of caller.
        want = set(self.steps)
        self.steps = [s.name for s in self.pipeline.order() if s.name in want]

    @property
    def stem(self) -> str:
        return self.input_path.stem

    @property
    def label(self) -> str:
        return self.input_path.name

    @property
    def values(self) -> dict[str, str]:
        """The full arg values for this run: the run identity plus the tunables."""
        return {
            "stem": self.stem,
            "output": str(self.output_base),
            "input": str(self.input_path),
            **self.settings,
        }

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
