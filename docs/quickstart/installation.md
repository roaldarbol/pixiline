# Installation

Pixiline is a small [PySide6](https://doc.qt.io/qtforpython/) desktop app. It
carries **no pipeline dependencies of its own** — the pipelines you run bring their
own Pixi environments — so installing Pixiline is quick.

## Recommended: `pixi global`

Install Pixiline as a global command-line app with [Pixi](https://pixi.sh), from
the `sleeb-forge` channel (until it lands on conda-forge):

```bash
pixi global install pixiline -c https://prefix.dev/sleeb-forge
```

This puts a `pixiline` command on your `PATH` and registers the app in the usual
places (see [Launch](launch.md)).

!!! note "Coming to conda-forge"
    Pixiline is on its way to **conda-forge**. Once it lands you'll be able to drop
    the channel flag and just `pixi global install pixiline`.

## From a checkout (for development)

Pixiline is developed as a Pixi workspace, so [Pixi](https://pixi.sh) handles the
environment for you:

```bash
git clone https://github.com/roaldarbol/pixiline
cd pixiline
pixi run pixiline
```

`pixi run pixiline` builds the environment on first run and launches the app.

## Requirements

- **Python 3.11+** (supplied by the Pixi environment).
- A working **`pixi`** on your `PATH` — Pixiline shells out to it to read each
  pipeline's tasks and to run them. Install it from
  [pixi.sh](https://pixi.sh/latest/#installation).

!!! note "Pixiline needs `pixi`, not the other way round"
    Pixiline **runs** your pipelines by calling `pixi run` under the hood. It never
    modifies a pipeline's `pixi.toml`; it only reads it. If `pixi` isn't found,
    loading a pipeline will fail with a clear message.
