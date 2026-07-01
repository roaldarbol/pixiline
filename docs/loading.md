# Loading pipelines

A **pipeline** is just a Pixi workspace: a folder with a `pixi.toml` whose
`[tasks]` are the pipeline's steps. Pixiline loads that manifest, reads the steps
and their dependency graph, and gives you a workbench to run it from.

## Add a pipeline

There are two ways to load one, and you can load as many as you like:

- **Drop it on the window.** Drag a pipeline's `pixi.toml` — or the folder that
  contains one — onto Pixiline. Dropping a folder finds the `pixi.toml` inside it.
- **Browse to it.** Click **Add pipeline…** in the sidebar and pick a `pixi.toml`.

Each loaded pipeline appears in the **Pipelines** list on the left. Selecting one
makes it the **active** pipeline, whose workbench fills the rest of the window.

![The Pipelines sidebar and workbench](assets/app-pipeline-light.png#only-light){ loading=lazy }
![The Pipelines sidebar and workbench](assets/app-pipeline-dark.png#only-dark){ loading=lazy }

## Several at once

Pixiline is built for juggling more than one pipeline:

- **Load many.** Add as many pipelines as you need — they stack in the sidebar, and
  each keeps its own destination, selected steps, settings, and input list.
- **Rename.** Double-click a pipeline in the list to give it a friendlier name (the
  name is only a display alias; it doesn't touch the `pixi.toml`).
- **Duplicate by re-adding.** Load the same `pixi.toml` twice to run it two ways —
  Pixiline gives the second one a numbered name so they stay distinct.
- **Remove.** Select a pipeline and click **Remove** to drop it from the list.

Every pipeline you load feeds the **same** [Jobs queue](jobs.md), so you can stage
work from several pipelines and run it all from one place.

## What makes a valid pipeline?

When Pixiline loads a `pixi.toml`, it looks for tasks that declare **`inputs`
and/or `outputs`** — those are the pipeline's *steps*. Plain helper tasks (a
`lint`, a `gui`, anything with no `inputs`/`outputs`) and hidden tasks (names
starting with `_`) are ignored.

If a manifest has no such tasks, Pixiline still loads it but tells you it declares
no steps. To learn how to write tasks that Pixiline can drive, see
**[Writing a pipeline](writing-a-pipeline/index.md)**.

!!! note "Read-only"
    Loading a pipeline never changes its files. Pixiline reads the manifest via
    `pixi task list` and runs tasks via `pixi run`; your `pixi.toml` is the single
    source of truth and stays untouched.
