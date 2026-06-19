"""Read the pipeline definition from config.yaml, and turn a step into a command.

The pipeline is the ordered ``steps:`` list in config.yaml. Each step declares the
files it ``needs`` and the file/dir it ``makes`` (inline patterns; ``{stem}`` is the
recording id, a bare glob like ``*.mp4`` is an external file the user supplies).
The GUI shows the steps in order; every step is invoked the same way:

    pixi run -e <env> <name> -- --stem <stem> --output <base> [--input <path>] [--overwrite]

``--input`` is passed only when a step needs an external (non-``{stem}``) input.
"""

from __future__ import annotations

from dataclasses import dataclass
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
            )
        )
    return tuple(steps)


def step_by_name() -> dict[str, Step]:
    return {s.name: s for s in discover_steps()}


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
        pixi_executable(), "run", "-e", env, step_name,
        "--", "--stem", stem, "--output", str(output_base),
    ]
    if step is not None and step.wants_input:
        cmd += ["--input", str(input_path)]
    if overwrite:
        cmd.append("--overwrite")
    return cmd


def working_directory() -> str:
    return str(PIPELINE_ROOT)
