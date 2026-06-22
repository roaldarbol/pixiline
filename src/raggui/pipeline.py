"""Read the pipeline definition from config.yaml, and turn a step into a command.

The pipeline is the ordered ``steps:`` list in config.yaml. Each step declares the
files it ``needs`` and the file/dir it ``makes`` (inline patterns; ``{stem}`` is the
recording id, a bare glob like ``*.mp4`` is an external file the user supplies).
The GUI shows the steps in order; every step is invoked the same way:

    pixi run -e <env> <name> -- --stem <stem> --output <base> [--input <path>] [--overwrite]

``--input`` is passed only when a step needs an external (non-``{stem}``) input.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path

from ruamel.yaml import YAML

from raggui.paths import CONFIG_PATH, PIPELINE_ROOT, pixi_executable

_yaml = YAML(typ="safe")

#: The reserved config.yaml key that holds the pipeline definition.
STEPS_KEY = "steps"


def _is_external(pattern: str) -> bool:
    """A need is external (user-supplied file) when it isn't located in the output
    tree — i.e. it has no ``{stem}`` placeholder."""
    return "{stem}" not in pattern


@dataclass(frozen=True)
class Step:
    name: str
    env: str
    needs: tuple[str, ...]
    makes: str
    optional: bool = False  # a side-branch step; off by default, nothing depends on it

    @property
    def label(self) -> str:
        return self.name.replace("-", " ").replace("_", " ").strip().title()

    @property
    def wants_input(self) -> bool:
        """Whether this step consumes an external (user-supplied) file."""
        return any(_is_external(n) for n in self.needs)


@lru_cache(maxsize=1)
def discover_steps() -> tuple[Step, ...]:
    """The pipeline's steps, in declared order. Empty if config.yaml can't be read
    or has no ``steps:`` list."""
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data = _yaml.load(fh)
        raw = (data or {}).get(STEPS_KEY) or []
    except (OSError, ValueError):
        return ()
    steps: list[Step] = []
    for item in raw:
        if not isinstance(item, dict) or "name" not in item:
            continue
        needs = item.get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        steps.append(
            Step(
                name=str(item["name"]),
                env=str(item.get("env", "")),
                needs=tuple(str(n) for n in needs),
                makes=str(item.get("makes", "")),
                optional=bool(item.get("optional", False)),
            )
        )
    return tuple(steps)


def step_by_name() -> dict[str, Step]:
    return {s.name: s for s in discover_steps()}


@lru_cache(maxsize=1)
def available_envs() -> frozenset[str]:
    """The pixi environments that actually exist (defined in pixi.toml). A step
    whose ``env`` isn't here can't run — e.g. it was commented out. Empty if pixi
    can't be queried, in which case callers should not gate on it."""
    try:
        proc = subprocess.run(
            [pixi_executable(), "info", "--json"],
            cwd=str(PIPELINE_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return frozenset()
    return frozenset(e.get("name", "") for e in data.get("environments_info", []))


def env_available(env: str) -> bool:
    """Whether ``env`` is usable. If pixi couldn't be queried (empty set) we don't
    gate on it, to avoid disabling everything when offline."""
    envs = available_envs()
    return (not envs) or (env in envs)


def accepted_input_globs() -> list[str]:
    """File globs the pipeline accepts as an external input, gathered from every
    step's external (non-``{stem}``) needs. Each need may be a comma-separated list
    (e.g. ``"*.mp4, *.mov"``). De-duplicated, in declared order. Empty if none."""
    globs: list[str] = []
    for step in discover_steps():
        for need in step.needs:
            if _is_external(need):
                for part in need.split(","):
                    g = part.strip()
                    if g and g not in globs:
                        globs.append(g)
    return globs


def ordered(step_names: set[str]) -> list[str]:
    """Return the given step names in declared (config.yaml) order."""
    index = {s.name: i for i, s in enumerate(discover_steps())}
    return sorted((n for n in step_names if n in index), key=lambda n: index[n])


# --- runnability planning ----------------------------------------------------
#
# A step can be *started* only when every one of its needs is available without
# running any pipeline step: an external need (a glob) is met when the chosen
# input file matches it; an artifact need (a "{stem}/…" pattern) is met when that
# file/dir already exists under the output base. Downstream, an artifact need is
# also met if an earlier *selected* step makes it. This drives the GUI's gating:
# the selection must be a contiguous run from a legal start, with no holes.


def artifact_present(pattern: str, output_base: Path | None, stem: str) -> bool:
    """Whether the artifact a ``{stem}`` pattern points to exists under the output
    base. Supports globs (``*`` etc.), since some tools name outputs dynamically
    (e.g. octron's ``<label>_track_1.csv``)."""
    if output_base is None:
        return False
    rel = pattern.replace("{stem}", stem)
    if any(ch in rel for ch in "*?["):
        try:
            return any(output_base.glob(rel))
        except (OSError, ValueError):
            return False
    return (output_base / rel).exists()


def _need_met_at_rest(need: str, input_name: str, output_base: Path | None, stem: str) -> bool:
    """Whether a single need is satisfiable without running any step."""
    if _is_external(need):
        if not input_name:
            return False
        return any(
            fnmatch(input_name.lower(), part.strip().lower())
            for part in need.split(",")
            if part.strip()
        )
    return artifact_present(need, output_base, stem)


def need_met(
    need: str,
    input_path: Path | None,
    output_base: Path | None,
    stem: str,
    produced: frozenset[str] = frozenset(),
) -> bool:
    """Whether a need is satisfied: available at rest (input/disk) OR produced by an
    already-selected step (``produced`` is a set of those steps' ``makes``)."""
    name = input_path.name if input_path else ""
    return _need_met_at_rest(need, name, output_base, stem) or (need in produced)


def step_plan(
    input_path: Path | None,
    output_base: Path | None,
    stem: str,
    steps: tuple[Step, ...] | None = None,
) -> tuple[list[bool], list[int]]:
    """Per-step runnability for the current input + on-disk artifacts, over an
    ordered list of steps (defaults to the whole pipeline; the GUI passes just the
    *required* steps so optional ones don't gate the contiguous chain).

    Returns ``(legal, reach)`` indexed by position in ``steps``:
    - ``legal[i]``  — step i can be the first step run (all needs met at rest).
    - ``reach[i]``  — the furthest end index of a contiguous runnable run starting
      at i (``i-1`` if i itself can't start).
    """
    if steps is None:
        steps = discover_steps()
    name = input_path.name if input_path else ""

    def met_at_rest(need: str) -> bool:
        return _need_met_at_rest(need, name, output_base, stem)

    # A step can only run if its environment exists AND its needs are satisfied.
    legal = [env_available(s.env) and all(met_at_rest(n) for n in s.needs) for s in steps]

    reach: list[int] = []
    for start in range(len(steps)):
        made: set[str] = set()
        end = start - 1
        for k in range(start, len(steps)):
            step = steps[k]
            if not env_available(step.env) or not all(
                met_at_rest(n) or n in made for n in step.needs
            ):
                break
            made.add(step.makes)
            end = k
        reach.append(end)
    return legal, reach


def missing_needs(step: Step, input_path: Path | None, output_base: Path, stem: str) -> list[str]:
    """The step's needs that are not present right now (external input missing, or
    an artifact not yet on disk). Used by the worker to fail fast before running."""
    name = input_path.name if input_path else ""
    return [n for n in step.needs if not _need_met_at_rest(n, name, output_base, stem)]


def build_command(
    step_name: str,
    input_path: Path,
    output_base: Path,
    stem: str,
    *,
    overwrite: bool = False,
) -> list[str]:
    """The argv to run one step, via ``pixi run``. ``--input`` is added only when
    the step consumes an external file. Run with the workspace root as cwd."""
    step = step_by_name().get(step_name)
    env = step.env if step is not None else ""
    cmd = [
        pixi_executable(),
        "run",
        "-e",
        env,
        step_name,
        "--",
        "--stem",
        stem,
        "--output",
        str(output_base),
    ]
    if step is not None and step.wants_input:
        cmd += ["--input", str(input_path)]
    if overwrite:
        cmd.append("--overwrite")
    return cmd


def working_directory() -> str:
    return str(PIPELINE_ROOT)
