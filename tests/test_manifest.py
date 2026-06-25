"""Tests for the data layer: parsing a pipeline and the graph/glob logic."""

from __future__ import annotations

import json
import subprocess

import pytest

from conftest import make_step
from pixiline import manifest
from pixiline.manifest import (
    Arg,
    Pipeline,
    artifact_present,
    build_command,
    is_external_input,
    load_pipeline,
    resolve,
    step_inputs_met,
)

# --- Arg --------------------------------------------------------------------


def test_arg_required_when_no_default():
    assert Arg("input").required is True
    assert Arg("fps", default="30").required is False


# --- Step -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [("motion", "Motion"), ("motion-colour", "Motion Colour"), ("sleep_staging", "Sleep Staging")],
)
def test_step_label_titlecases_and_normalises_separators(name, expected):
    assert make_step(name).label == expected


def test_step_optional_detects_tag_case_insensitively():
    assert make_step("a", description="[OPTIONAL] side branch").optional is True
    assert make_step("a", description="a normal step").optional is False


def test_step_partitions_required_and_setting_args():
    step = make_step(
        "motion",
        args=(Arg("input"), Arg("fps", default="30"), Arg("model", default="base")),
    )
    assert [a.name for a in step.required_args] == ["input"]
    assert [a.name for a in step.setting_args] == ["fps", "model"]


# --- Pipeline ---------------------------------------------------------------


def test_pipeline_title_titlecases(sample_pipeline):
    assert sample_pipeline.title == "Spider Sleep"


def test_pipeline_step_lookup(sample_pipeline):
    assert sample_pipeline.step("track").name == "track"
    assert sample_pipeline.step("nope") is None


def test_default_settings_collects_every_tunable(sample_pipeline):
    assert sample_pipeline.default_settings() == {
        "fps": "30",
        "model": "base",
        "threshold": "0.5",
    }


def test_default_settings_first_default_wins_on_name_clash(tmp_path):
    a = make_step("a", args=(Arg("k", default="1"),), outputs=("o1",))
    b = make_step("b", args=(Arg("k", default="2"),), inputs=("x",))
    pipeline = Pipeline(root=tmp_path, name="p", steps=(a, b))
    assert pipeline.default_settings() == {"k": "1"}


def test_edges_match_outputs_to_inputs(sample_pipeline):
    assert set(sample_pipeline.edges()) == {
        ("motion", "track"),
        ("track", "export"),
        ("export", "report"),
    }


def test_order_is_topological_and_stable(sample_pipeline):
    assert [s.name for s in sample_pipeline.order()] == ["motion", "track", "export", "report"]


def test_order_raises_on_cycle(tmp_path):
    a = make_step("a", inputs=("b.out",), outputs=("a.out",))
    b = make_step("b", inputs=("a.out",), outputs=("b.out",))
    pipeline = Pipeline(root=tmp_path, name="p", steps=(a, b))
    with pytest.raises(ValueError, match="cycle"):
        pipeline.order()


def test_required_inputs_deduped_in_first_seen_order(tmp_path):
    a = make_step("a", args=(Arg("input"),), inputs=("{{ input }}",), outputs=("a.out",))
    b = make_step("b", args=(Arg("input"), Arg("extra")), inputs=("a.out",), outputs=("b.out",))
    pipeline = Pipeline(root=tmp_path, name="p", steps=(a, b))
    assert [a.name for a in pipeline.required_inputs()] == ["input", "extra"]


# --- _produces / glob matching ----------------------------------------------


@pytest.mark.parametrize(
    ("output", "input", "expected"),
    [
        ("dir/a.csv", "dir/a.csv", True),  # exact
        ("dir/**", "dir/sub/a.csv", True),  # tree glob covers anything beneath
        ("dir/*.csv", "dir/a.csv", True),  # plain glob
        ("dir/a.csv", "dir/b.csv", False),  # different file
        ("dir/*.csv", "dir/a.parquet", False),  # extension mismatch
        # directional: a consumer's broad input must not pull a narrower output
        ("bytetrack/x.csv", "bytetrack/**", False),
    ],
)
def test_produces_direction_and_globs(output, input, expected):
    assert manifest._produces(output, input) is expected


def test_is_external_input_detects_input_template():
    assert is_external_input("{{ input }}") is True
    assert is_external_input("{{ output }}/{{ stem }}/x.csv") is False


def test_resolve_substitutes_known_and_leaves_unknown():
    out = resolve("{{ output }}/{{ stem }}/{{ unknown }}.csv", {"output": "/o", "stem": "clip"})
    assert out == "/o/clip/{{ unknown }}.csv"


# --- artifact_present --------------------------------------------------------


def test_artifact_present_false_without_output_base():
    assert artifact_present("{{ output }}/x", None, "clip") is False


def test_artifact_present_exact_path(tmp_path):
    target = tmp_path / "clip" / "track.csv"
    pattern = "{{ output }}/{{ stem }}/track.csv"
    assert artifact_present(pattern, tmp_path, "clip") is False
    target.parent.mkdir(parents=True)
    target.write_text("data")
    assert artifact_present(pattern, tmp_path, "clip") is True


def test_artifact_present_glob(tmp_path):
    (tmp_path / "clip").mkdir()
    (tmp_path / "clip" / "a.csv").write_text("x")
    assert artifact_present("{{ output }}/{{ stem }}/*.csv", tmp_path, "clip") is True
    assert artifact_present("{{ output }}/{{ stem }}/*.parquet", tmp_path, "clip") is False


# --- step_inputs_met --------------------------------------------------------


def test_step_inputs_met_external_input_requires_user_file(sample_pipeline):
    motion = sample_pipeline.step("motion")
    common = {"output_base": None, "stem": "clip", "produced": set()}
    assert step_inputs_met(motion, has_input=True, **common) is True
    assert step_inputs_met(motion, has_input=False, **common) is False


def test_step_inputs_met_satisfied_by_produced_output(sample_pipeline):
    track = sample_pipeline.step("track")
    assert (
        step_inputs_met(
            track,
            has_input=True,
            output_base=None,
            stem="clip",
            produced={"{{ output }}/{{ stem }}/motion.mp4"},
        )
        is True
    )


def test_step_inputs_met_satisfied_by_artifact_on_disk(tmp_path, sample_pipeline):
    track = sample_pipeline.step("track")
    art = tmp_path / "clip" / "motion.mp4"
    art.parent.mkdir(parents=True)
    art.write_text("x")
    assert (
        step_inputs_met(track, has_input=True, output_base=tmp_path, stem="clip", produced=set())
        is True
    )


def test_step_inputs_met_unsatisfied(sample_pipeline):
    track = sample_pipeline.step("track")
    assert (
        step_inputs_met(track, has_input=True, output_base=None, stem="clip", produced=set())
        is False
    )


# --- load_pipeline (subprocess mocked) --------------------------------------


_TASK_LIST_JSON = [
    {
        "environment": "gpu",
        "features": [
            {
                "tasks": [
                    {
                        "name": "motion",
                        "description": "Detect motion",
                        "inputs": ["{{ input }}"],
                        "outputs": ["{{ output }}/{{ stem }}/motion.mp4"],
                        "args": [
                            {"name": "input"},
                            {"name": "fps", "default": "30"},
                            {"name": "model", "default": "base", "choices": ["base", "large"]},
                        ],
                    },
                    {"name": "_hidden", "inputs": ["x"], "outputs": ["y"]},
                    {"name": "probe-fps", "description": "helper, no io"},
                ]
            }
        ],
    },
    {
        "environment": "cpu",
        "features": [
            {
                "tasks": [
                    {
                        "name": "export",
                        "outputs": ["{{ output }}/{{ stem }}/export.parquet"],
                        "inputs": ["{{ output }}/{{ stem }}/motion.mp4"],
                    }
                ]
            }
        ],
    },
]


@pytest.fixture
def fake_pixi(monkeypatch, tmp_path):
    (tmp_path / "pixi.toml").write_text('[workspace]\nname = "my-pipeline"\n')

    def fake_run(argv, **kwargs):
        assert argv[1:3] == ["task", "list"]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(_TASK_LIST_JSON), stderr="")

    monkeypatch.setattr(manifest.subprocess, "run", fake_run)
    return tmp_path


def test_load_pipeline_parses_steps_and_skips_non_steps(fake_pixi):
    pipeline = load_pipeline(fake_pixi)
    assert pipeline.name == "my-pipeline"
    assert {s.name for s in pipeline.steps} == {"motion", "export"}  # _hidden + helper dropped
    assert pipeline.environments == frozenset({"gpu", "cpu"})


def test_load_pipeline_parses_args_and_env(fake_pixi):
    pipeline = load_pipeline(fake_pixi)
    motion = pipeline.step("motion")
    assert motion.env == "gpu"
    assert motion.args[0] == Arg("input")
    assert motion.args[2] == Arg("model", default="base", choices=("base", "large"))


def test_workspace_name_falls_back_to_dir_name(tmp_path):
    # No pixi.toml -> name is the directory name.
    assert manifest._workspace_name(tmp_path) == tmp_path.name


# --- build_command ----------------------------------------------------------


def test_build_command_uses_quiet_env_and_step(sample_pipeline):
    motion = sample_pipeline.step("motion")
    argv = build_command(motion, {"input": "/data/clip.mp4", "fps": "60", "model": "large"})
    assert argv == ["pixi", "run", "-q", "-e", "gpu", "motion", "/data/clip.mp4", "60", "large"]


def test_build_command_falls_back_to_defaults_then_empty(sample_pipeline):
    motion = sample_pipeline.step("motion")
    # Only the required arg supplied; fps -> default, model -> default.
    argv = build_command(motion, {"input": "/data/clip.mp4"})
    assert argv[-3:] == ["/data/clip.mp4", "30", "base"]


def test_build_command_honours_custom_pixi_exe(sample_pipeline):
    argv = build_command(sample_pipeline.step("export"), {}, pixi_exe="/opt/pixi")
    assert argv[0] == "/opt/pixi"
