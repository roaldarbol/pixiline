"""Tests for the Job model (pure data; no Qt)."""

from __future__ import annotations

from pathlib import Path

from pixiline.jobs.job import _LOG_CHAR_CAP, Job, JobState


def make_job(sample_pipeline, steps, **kwargs) -> Job:
    return Job(
        pipeline=sample_pipeline,
        input_path=Path("/data/clip.mp4"),
        output_base=Path("/out"),
        steps=steps,
        **kwargs,
    )


def test_post_init_sorts_steps_into_dependency_order(sample_pipeline):
    # Given out of order, the job re-sorts into topological order.
    job = make_job(sample_pipeline, steps=["export", "motion", "track"])
    assert job.steps == ["motion", "track", "export"]


def test_post_init_keeps_only_requested_steps(sample_pipeline):
    job = make_job(sample_pipeline, steps=["export", "motion"])
    assert job.steps == ["motion", "export"]


def test_stem_and_label(sample_pipeline):
    job = make_job(sample_pipeline, steps=["motion"])
    assert job.stem == "clip"
    assert job.label == "clip.mp4"


def test_values_merge_identity_and_settings_as_posix(sample_pipeline):
    job = make_job(sample_pipeline, steps=["motion"], settings={"fps": "60"})
    values = job.values
    assert values["stem"] == "clip"
    assert values["fps"] == "60"
    # Paths are POSIX so templated globs never mix separators.
    assert values["input"] == "/data/clip.mp4"
    assert values["output"] == "/out"
    assert "\\" not in values["output"]


def test_current_step_name_tracks_index(sample_pipeline):
    job = make_job(sample_pipeline, steps=["motion", "track"])
    assert job.current_step_name() == "motion"
    job.current_step = 1
    assert job.current_step_name() == "track"
    job.current_step = 2  # past the end
    assert job.current_step_name() is None


def test_fraction_progresses_and_clamps(sample_pipeline):
    job = make_job(sample_pipeline, steps=["motion", "track", "export"])
    assert job.fraction() == 0.0
    job.current_step = 3
    assert job.fraction() == 1.0
    job.current_step = 99  # clamps
    assert job.fraction() == 1.0


def test_fraction_zero_when_no_steps(sample_pipeline):
    job = make_job(sample_pipeline, steps=[])
    assert job.fraction() == 0.0


def test_append_log_is_bounded(sample_pipeline):
    job = make_job(sample_pipeline, steps=["motion"])
    job.append_log("a" * 10)
    assert job.log == "a" * 10
    job.append_log("b" * (_LOG_CHAR_CAP + 50))
    assert len(job.log) == _LOG_CHAR_CAP
    assert job.log.endswith("b")  # newest output kept, oldest dropped


def test_jobs_get_unique_incrementing_ids(sample_pipeline):
    j1 = make_job(sample_pipeline, steps=["motion"])
    j2 = make_job(sample_pipeline, steps=["motion"])
    assert j2.id > j1.id


def test_default_state_is_queued(sample_pipeline):
    assert make_job(sample_pipeline, steps=["motion"]).state is JobState.QUEUED
