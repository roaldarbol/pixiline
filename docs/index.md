# Pixiline

[![Tests](https://github.com/roaldarbol/pixiline/actions/workflows/tests.yml/badge.svg)](https://github.com/roaldarbol/pixiline/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://github.com/roaldarbol/pixiline)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://github.com/roaldarbol/pixiline/blob/main/LICENSE)

Pixiline is a **desktop app that runs and monitors any [Pixi](https://pixi.sh)-defined
pipeline locally** — the `[tasks]` in a `pixi.toml` *are* the pipeline, and Pixiline
gives them a GUI.

![The pipeline workbench](assets/app-pipeline-light.png#only-light){ loading=lazy }
![The pipeline workbench](assets/app-pipeline-dark.png#only-dark){ loading=lazy }

!!! warning "An independent, community project"
    Pixiline is **not** an official Prefix.dev product and is **not affiliated with,
    endorsed by, or supported by** the [Pixi](https://pixi.sh) project or
    [Prefix.dev](https://prefix.dev). It is an independent, MIT-licensed tool that
    *uses* Pixi. "Pixi" and the Pixi logo belong to their respective owners; the
    Pixi-inspired colours here are a nod, not a claim of association.

## Highlights

- 🧩 **[The manifest *is* the pipeline](writing-a-pipeline/index.md)** — steps are
  ordinary Pixi tasks in a `pixi.toml`; the dependency graph is derived from their
  `inputs`/`outputs`. No new workflow language, no `config.yaml`, no wrapper scripts.
- 🕹️ **A GUI for any Pixi workspace** — load a pipeline, pick steps and inputs,
  queue, and run — without writing a line of UI code.
- 🔀 **[A dependency-aware DAG](steps.md)** — Pixiline draws the graph, runs steps in
  order, and skips any whose inputs aren't ready.
- 🎛️ **[Auto-generated settings](inputs.md#settings)** — typed task args become a
  form, with defaults and dropdowns.
- ▶️ **[Queue & monitor](jobs.md)** — batch jobs, run several in parallel, watch a
  live colour terminal, and cancel the whole process tree.
- ⏭️ **Skip what's done** — reuses Pixi's up-to-date caching, so re-runs only do the
  work that's actually new.
- 📝 **[Every run is logged](jobs.md#logs-on-disk)** — a clean, settled plain-text
  log is saved next to each run's outputs (plus a session log for the app), so you
  keep a durable record long after the terminal is closed.
- 🪶 **No stack of its own** — Pixiline carries no pipeline dependencies; each
  pipeline brings its own Pixi environments.

New here? Install it in the [Quickstart](quickstart/installation.md), then read
[Steps & the DAG](steps.md) for the model the rest of the app is built on.

## Where Pixiline fits

Pixiline sits between two familiar options: running `pixi run` by hand in a
terminal, and reaching for a full workflow manager. If your work already lives in a
Pixi workspace, Pixiline gives those tasks a GUI — a DAG, a settings form, a job
queue, and a live terminal — with **no new workflow language and no second copy of
the pipeline**. It's built for one machine at a time: a workstation or a laptop.

Reach for a dedicated workflow system when you outgrow that. Tools like
[Snakemake](https://snakemake.github.io/), [Nextflow](https://www.nextflow.io/) (with
community pipelines via [nf-core](https://nf-co.re/)),
[Galaxy](https://galaxyproject.org/), or [CWL](https://www.commonwl.org/) are the
right call when you need to **scale across an HPC cluster or the cloud**, fan out over
thousands of samples, or want publication-grade provenance and portability. Pixiline
doesn't try to replace those **yet** — it's the friendly local front-end for the Pixi
tasks you'd otherwise run one by one.

## Useful links

- 📘 **[Pixi documentation](https://pixi.sh)** — the workspace & task runner Pixiline
  drives.
- 🛠️ **[Pixi tasks guide](https://pixi.sh/latest/workspace/advanced_tasks/)** — how
  `[tasks]` work, which is the heart of a Pixiline pipeline.
- 📄 **[Pixi manifest reference](https://pixi.sh/latest/reference/pixi_manifest/)** —
  the full `pixi.toml` schema (`args`, `inputs`, `outputs`, environments).
- ✍️ **[Writing a pipeline](writing-a-pipeline/index.md)** — build one up from a
  single task to a branching graph.
- 📦 **[prefix.dev](https://prefix.dev)** — the conda package index that hosts
  Pixiline's `sleeb-forge` channel.
- 🌱 **[conda-forge](https://conda-forge.org)** — the community conda package index
  Pixiline is on its way to.
- 🐙 **[Pixiline on GitHub](https://github.com/roaldarbol/pixiline)** — source,
  issues, and a place to leave a star.
