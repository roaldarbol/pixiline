<p align="center">
  <img src="src/pixiline/assets/orchestrator.png" alt="pixiline logo" width="200">
</p>

<h1 align="center">pixiline</h1>

<p align="center">
  <em>Run and monitor any Pixi-defined pipeline from one window.</em>
</p>

<p align="center">
  <a href="https://github.com/roaldarbol/pixiline/actions/workflows/tests.yml"><img src="https://github.com/roaldarbol/pixiline/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://codecov.io/gh/roaldarbol/pixiline"><img src="https://codecov.io/gh/roaldarbol/pixiline/graph/badge.svg" alt="Coverage"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

pixiline turns a [Pixi](https://pixi.sh) workspace into a runnable pipeline you can drive from a GUI. Point it at a pipeline's `pixi.toml` — whose `[tasks]` *are* the pipeline steps — and it reads the steps, their inputs and tunable settings, and the dependency graph between them. Pick what to run and what to run it on, queue the jobs, and watch them execute in a live colour terminal you can cancel from.

It's organized like an editor: a VSCode-style **activity bar** switches between a **Pipelines** view (the loaded pipelines and the active one's workbench) and a single, app-wide **Jobs** view (the queue/monitor shared by every pipeline). You can load several pipelines side by side and run jobs from any of them into the same queue.

pixiline owns the **orchestration and monitoring** layer only — the queue, dependency-aware step gating, process-tree-safe cancellation, per-run and per-session logging, and the terminal. It carries **no pipeline dependencies of its own**: each pipeline is its own Pixi workspace with its own environments and tasks, and pixiline simply runs them via `pixi`.

## What you can do

- **Load pipelines** — drop a `pixi.toml` (or a folder containing one) onto the window, or use **Add pipeline…**. Each loaded pipeline appears in the left list; you can rename or duplicate them and load as many as you like.
- **Pick steps** — the **Steps** tab lists every runnable step (a `[tasks.<name>]` with `inputs`/`outputs`) and shows how they connect as a **DAG** derived from matching one step's outputs to another's inputs. Step gating is dependency-aware, so you only run what's ready.
- **Choose inputs** — the **Inputs** tab is where you pick the files/recordings to run on and the output directory; they apply across the pipeline.
- **Tune settings** — the **Settings** tab is generated from each task's typed `args` (defaults and `choices`), so a pipeline's knobs become a form without any extra config.
- **Queue and run** — **Add to Queue** stages jobs; the **Jobs** view collects everything from every pipeline. **Start all** or tick rows and **Start selected**; **Cancel** stops a running job (killing the whole process tree), **Remove selected** drops staged ones, and **Clear finished** tidies up.
- **Run in parallel** — a **Parallel (up to N)** toggle runs several jobs at once, with the worker count suggested from your machine.
- **Watch it happen** — every run streams to a live terminal with real ANSI colour and in-place progress, and a slim status strip along the bottom always shows counts + progress from whichever view you're on.
- **Skip what's done** — because steps declare `inputs`/`outputs` globs, Pixi's up-to-date caching is reused to skip work that's already current.

## The pipeline model

A pipeline is described entirely by its `pixi.toml` — there is no `config.yaml` and no per-step wrapper scripts:

- a **step** is a `[tasks.<name>]` with an environment (the feature it runs under),
  typed `args` (the run identity plus tunable knobs with `default`/`choices`),
  `inputs`/`outputs` globs, and a `description`.
- the **dependency graph** is derived by matching one step's `outputs` to another
  step's `inputs` — no separate graph file.
- the **Settings** form and the **Steps** DAG are both generated from that metadata.

`pixi.toml` is the single source of truth.

## Install

pixiline is built as a conda package (with [rattler-build](https://rattler.build)). Once published you'll be able to:

```bash
pixi add pixiline
# or
conda install -c conda-forge pixiline
```

In the meantime, run it straight from a checkout — [pixi](https://pixi.sh) handles the environment:

```bash
git clone https://github.com/roaldarbol/pixiline
cd pixiline
pixi run pixiline
```

## Using it

```bash
pixiline   # opens with no pipeline loaded
```

1. **Add a pipeline** — drag a pipeline's `pixi.toml` (or its folder) onto the window, or click **Add pipeline…**. It joins the list on the left.
2. **Set it up** — in the active pipeline's workbench, choose what to run in **Steps**, the files and output directory in **Inputs**, and any knobs in **Settings**.
3. **Queue it** — **Add to Queue** stages the jobs for the steps you picked.
4. **Run it** — switch to the **Jobs** view and **Start all** (or **Start selected**). Watch the live terminal, flip **Parallel** on to run several at once, and **Cancel** anything you need to.

## Contributing

The codebase is small and meant to stay readable. Layout:

```text
src/pixiline/app.py        # Qt application entry point (the `pixiline` command)
src/pixiline/manifest.py   # parse a pipeline's pixi.toml into steps + the DAG
src/pixiline/gui/          # PySide6 widgets: activity bar, pipelines sidebar,
                           #   pipeline workbench (Inputs/Steps/Settings), DAG view,
                           #   jobs panel, colour terminal, theming
src/pixiline/jobs/         # job queue + per-job worker (process-tree-safe cancel),
                           #   settled terminal logging
src/pixiline/config.py     # QSettings persistence (output dir, parallel toggle)
src/pixiline/{paths,resources,applog}.py  # pixi discovery, icons, session logging
```

To work on it from a checkout:

```bash
pixi run pixiline          # launch the app
pixi run -e dev test       # run the test suite (with coverage)
pixi run -e dev lint       # ruff check
pixi run -e dev format     # ruff format
```

Tests cover the orchestration core — the pipeline/graph model, the job model, the
queue state machine, the terminal log settler, and the small config/paths
helpers. The Qt widgets and the subprocess Worker are exercised by hand rather
than in CI.

## License

MIT — see [LICENSE](LICENSE).
