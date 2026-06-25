# pixiline

A generic **Pixi-pipeline manager** GUI. Point it at a pipeline's `pixi.toml`
(whose `[tasks]` are the pipeline steps), pick which steps to run and the inputs
to run them on, queue them, and watch them execute with a live terminal log.

pixiline owns the **orchestration/monitoring** layer only — the queue, step gating,
process-tree-safe cancellation, per-run + session logging, and a colour terminal.
It carries **no** pipeline dependencies; each pipeline is its own Pixi workspace
with its own environments and tasks.

## Run

```sh
pixi run pixiline
```

## The pipeline model

A pipeline is described entirely by its `pixi.toml`:

- a **step** is a `[tasks.<name>]` with an environment (the feature it's under),
  typed `args` (the run identity `stem`/`output`/`input` plus tunable knobs with
  `default`/`choices`), `inputs`/`outputs` globs, and a `description`.
- the **dependency graph** is derived by matching one step's `outputs` to another
  step's `inputs` (no separate graph file); the same globs drive Pixi's
  skip-if-up-to-date caching.
- the **Settings** form is generated from each task's `args`.

There is no `config.yaml` and no per-step wrapper scripts — `pixi.toml` is the
single source of truth.

## Example pipeline

[`./sleep-staging`](./sleep-staging) is a complete example: spider-sleep
segmentation (motion-colour → tracking → export → R analysis), defined purely as
Pixi tasks. It's a sibling workspace and is the temporary home of that pipeline
until it moves to its own repository.

## Layout

```
pixi.toml            # this app's env (PySide6 + helpers) and the `gui` task
src/pixiline/          # the GUI
src/tools/           # build helpers (icon generation)
sleep-staging/       # example pipeline workspace (own pixi.toml + resources)
```
