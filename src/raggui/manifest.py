"""Load a pipeline from a Pixi workspace.

A pipeline is described entirely by its ``pixi.toml``: each step is a
``[tasks.<name>]`` with typed ``args`` (the run identity + tunable knobs),
``inputs``/``outputs`` globs (which wire the dependency graph and drive Pixi's
caching), and a ``description``. We read all of that via ``pixi task list --json``
- there is no separate config file and no per-step wrapper scripts.

This module is the data layer only: it knows nothing about Qt. ``load_pipeline``
returns a :class:`Pipeline`; the GUI renders it and ``build_command`` turns a step
+ a set of values into the ``pixi run`` argv the worker launches.
"""

from __future__ import annotations

import fnmatch
import glob as _glob
import json
import re
import subprocess
import tomllib
from collections import deque
from dataclasses import dataclass
from pathlib import Path

_TEMPLATE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass(frozen=True)
class Arg:
    """One task argument. ``default is None`` means it is required (no default)."""

    name: str
    default: str | None = None
    choices: tuple[str, ...] | None = None

    @property
    def required(self) -> bool:
        return self.default is None


@dataclass(frozen=True)
class Step:
    """A pipeline step = a Pixi task with declared inputs/outputs."""

    name: str
    env: str  # the environment it runs in
    description: str
    args: tuple[Arg, ...]
    inputs: tuple[str, ...]  # templated globs ({{ stem }}, {{ output }}, ...)
    outputs: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.name.replace("-", " ").replace("_", " ").strip().title()

    @property
    def optional(self) -> bool:
        """A side-branch step the author marked ``[optional]`` in its description -
        off by default; toggled on its own (Pixi has no native 'optional' flag)."""
        return "[optional]" in self.description.lower()

    @property
    def required_args(self) -> tuple[Arg, ...]:
        """Args with no default - the run identity the user supplies (stem/output/input)."""
        return tuple(a for a in self.args if a.required)

    @property
    def setting_args(self) -> tuple[Arg, ...]:
        """Args with a default - the tunable knobs shown in the Settings tab."""
        return tuple(a for a in self.args if not a.required)


@dataclass(frozen=True)
class Pipeline:
    root: Path
    name: str
    steps: tuple[Step, ...]
    environments: frozenset[str] = frozenset()  # env names defined in the manifest

    @property
    def title(self) -> str:
        return self.name.replace("-", " ").replace("_", " ").strip().title()

    def step(self, name: str) -> Step | None:
        return next((s for s in self.steps if s.name == name), None)

    def default_settings(self) -> dict[str, str]:
        """Default value for every tunable (setting) arg across all steps, keyed by
        arg name. Shared by all of this pipeline's inputs."""
        values: dict[str, str] = {}
        for step in self.steps:
            for a in step.setting_args:
                values.setdefault(a.name, a.default or "")
        return values

    def edges(self) -> list[tuple[str, str]]:
        """Dependency edges A -> B, derived by matching A's outputs to B's inputs."""
        out = []
        for producer in self.steps:
            for consumer in self.steps:
                if producer.name == consumer.name:
                    continue
                if any(_produces(o, i) for o in producer.outputs for i in consumer.inputs):
                    out.append((producer.name, consumer.name))
        return out

    def order(self) -> list[Step]:
        """Steps in dependency (topological) order. Raises on a cycle."""
        edges = self.edges()
        indegree = {s.name: 0 for s in self.steps}
        adj: dict[str, list[str]] = {s.name: [] for s in self.steps}
        for a, b in edges:
            adj[a].append(b)
            indegree[b] += 1
        # Stable: preserve declaration order among ready nodes.
        ready = deque(s.name for s in self.steps if indegree[s.name] == 0)
        ordered: list[str] = []
        while ready:
            n = ready.popleft()
            ordered.append(n)
            for m in adj[n]:
                indegree[m] -= 1
                if indegree[m] == 0:
                    ready.append(m)
        if len(ordered) != len(self.steps):
            raise ValueError("pipeline has a dependency cycle")
        by_name = {s.name: s for s in self.steps}
        return [by_name[n] for n in ordered]

    def required_inputs(self) -> tuple[Arg, ...]:
        """The run-identity args (no default) across all steps, deduped by name and
        in first-seen order - e.g. stem, output, input."""
        seen: dict[str, Arg] = {}
        for step in self.order():
            for a in step.required_args:
                seen.setdefault(a.name, a)
        return tuple(seen.values())


def _produces(producer_output: str, consumer_input: str) -> bool:
    """Whether ``producer_output`` supplies ``consumer_input`` - i.e. the consumer
    reads (part of) what the producer wrote.

    Directional on purpose: the producer's output must *cover* the consumer's input,
    not the other way round. Otherwise two steps that write into the same directory
    (e.g. predict's ``bytetrack/**`` and export's ``bytetrack/*.csv``) would spawn a
    false edge. Handles exact matches, directory-tree globs (``dir/**`` covers
    anything under ``dir/``), and plain globs (``dir/*.csv`` covers ``dir/x.csv``).
    """
    o, i = producer_output.strip(), consumer_input.strip()
    if i == o:
        return True
    if o.endswith("/**") and i.startswith(o[:-2]):
        return True
    return fnmatch.fnmatch(i, o)


def is_external_input(pattern: str) -> bool:
    """Whether an input glob refers to the user-supplied file (``{{ input }}``)
    rather than something in the output tree."""
    return "input" in _TEMPLATE.findall(pattern)


def resolve(pattern: str, values: dict[str, str]) -> str:
    """Substitute ``{{ name }}`` placeholders from ``values`` (others left as-is)."""
    return _TEMPLATE.sub(lambda m: values.get(m.group(1), m.group(0)), pattern)


def artifact_present(pattern: str, output_base: Path | None, stem: str) -> bool:
    """Whether the artifact an output-tree glob points to already exists on disk."""
    if output_base is None:
        return False
    resolved = resolve(pattern, {"output": str(output_base), "stem": stem})
    if any(c in resolved for c in "*?["):
        try:
            return bool(_glob.glob(resolved, recursive=True))
        except OSError:
            return False
    return Path(resolved).exists()


def step_inputs_met(
    step: Step,
    *,
    has_input: bool,
    output_base: Path | None,
    stem: str,
    produced: set[str],
) -> bool:
    """Whether every input of ``step`` is satisfiable: the external user file is
    present, the artifact is already on disk, or a ``produced`` output glob (from
    the steps selected so far) covers it."""
    for pat in step.inputs:
        if is_external_input(pat):
            if not has_input:
                return False
            continue
        if artifact_present(pat, output_base, stem):
            continue
        if any(_produces(o, pat) for o in produced):
            continue
        return False
    return True


def clear_outputs(step: Step, output_base: Path, stem: str) -> list[str]:
    """Delete a step's declared output files for this run (the 'overwrite' action),
    so the step re-runs instead of being skipped as up to date. Only files **under
    ``output_base``** are removed, as a safety guard against a broad/odd glob."""
    deleted: list[str] = []
    base = str(output_base)
    for pat in step.outputs:
        resolved = resolve(pat, {"output": base, "stem": stem})
        if not resolved.startswith(base):
            continue  # never delete outside the chosen output base
        if any(c in resolved for c in "*?["):
            matches = _glob.glob(resolved, recursive=True)
        else:
            matches = [resolved] if Path(resolved).exists() else []
        for match in matches:
            path = Path(match)
            try:
                if path.is_file():
                    path.unlink()
                    deleted.append(match)
            except OSError:
                pass
    return deleted


def _workspace_name(root: Path) -> str:
    try:
        with (root / "pixi.toml").open("rb") as fh:
            return tomllib.load(fh).get("workspace", {}).get("name", root.name)
    except (OSError, tomllib.TOMLDecodeError):
        return root.name


def load_pipeline(root: Path, pixi_exe: str = "pixi") -> Pipeline:
    """Read ``root``'s Pixi manifest and build the pipeline model.

    Steps are the tasks that declare ``inputs`` and/or ``outputs`` (so helper tasks
    like ``probe-fps`` or ``gui`` are excluded), are not hidden (``_`` prefix), and
    each runs in the environment it is listed under.
    """
    proc = subprocess.run(
        [pixi_exe, "task", "list", "--manifest-path", str(root / "pixi.toml"), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)

    steps: dict[str, Step] = {}
    environments = frozenset(environment["environment"] for environment in data)
    for environment in data:
        env_name = environment["environment"]
        for feature in environment["features"]:
            for task in feature["tasks"]:
                name = task["name"]
                if name.startswith("_") or name in steps:
                    continue
                inputs = tuple(task.get("inputs") or ())
                outputs = tuple(task.get("outputs") or ())
                if not inputs and not outputs:
                    continue  # not a pipeline step (helper / plain task)
                args = tuple(
                    Arg(
                        name=a["name"],
                        default=a.get("default"),
                        choices=tuple(a["choices"]) if a.get("choices") else None,
                    )
                    for a in (task.get("args") or ())
                )
                steps[name] = Step(
                    name=name,
                    env=env_name,
                    description=task.get("description") or "",
                    args=args,
                    inputs=inputs,
                    outputs=outputs,
                )
    pipeline = Pipeline(
        root=root,
        name=_workspace_name(root),
        steps=tuple(steps.values()),
        environments=environments,
    )
    pipeline.order()  # validate (raises on cycle)
    return pipeline


def build_command(step: Step, values: dict[str, str], pixi_exe: str = "pixi") -> list[str]:
    """Build the ``pixi run`` argv for a step.

    Pixi task args are positional in declared order, so we pass a value for every
    arg: the caller's value if given, else the arg's default (or empty string).
    Returned as a list so process spawners handle spaces in paths.
    """
    argv = [pixi_exe, "run", "-e", step.env, step.name]
    for a in step.args:
        argv.append(values.get(a.name, a.default or ""))
    return argv
