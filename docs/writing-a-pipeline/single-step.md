# A single step

The smallest useful pipeline is a single task that takes the user's file and writes
one result. It's worth dwelling on, because everything larger is just more of this.

Our example downscales a video to 720p with `ffmpeg`:

```toml title="pixi.toml"
[workspace]
name = "resize-pipeline"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64", "win-64"]

[dependencies]
ffmpeg = ">=6"

[tasks.resize]
description = "Downscale a video to 720p."
args = ["input", "output", "stem"]                                     # (1)!
cmd = "ffmpeg -y -i {{ input }} -vf scale=-2:720 {{ output }}/{{ stem }}_small.mp4"
inputs = ["{{ input }}"]                                               # (2)!
outputs = ["{{ output }}/{{ stem }}_small.mp4"]                        # (3)!
```

1. All three are **required** (declared as bare names, so they have no default).
   Pixiline recognises `input`, `output`, and `stem` as the *run identity* and fills
   them from the file and Destination — so they never appear in the Settings form.
2. The step reads the **user file** — this is what makes it the pipeline's entry
   point.
3. It writes exactly one artifact, named after the input's `stem`.

## What Pixiline makes of it

Load this `pixi.toml` and you get a **one-node DAG** — a single `Resize` box, ticked
and ready. Because the only args are the run identity, the **Settings** card says the
pipeline exposes no settings. There's nothing to configure but the Destination and
the files.

Pick a Destination, drag in a few `.mp4` files, and **Add to Queue**. Each file
becomes one job that runs:

```bash
ffmpeg -y -i clip07.mp4 -vf scale=-2:720 <destination>/clip07_small.mp4
```

## The run identity, in detail

The three special args are the contract between Pixiline and your task:

| Arg        | For `holiday.MOV` into `D:/out`      |
| ---------- | ------------------------------------ |
| `input`    | the full path to `holiday.MOV`       |
| `output`   | `D:/out`                             |
| `stem`     | `holiday`                            |

Naming an output `{{ output }}/{{ stem }}_small.mp4` therefore keeps every file's
result separate and predictable. If two source files share a stem, they'd collide —
so lean on `{{ stem }}` (and, later, per-file subfolders) to stay unambiguous.

!!! tip "Keep outputs under `{{ output }}`"
    Always write beneath `{{ output }}`. A per-file **subfolder**
    (`{{ output }}/{{ stem }}/…`) is a tidy pattern once a step produces several
    files — just have the step create the folder first (e.g. a `mkdir -p` in the
    command), since `ffmpeg` and friends won't make it for you.

!!! note "Why declare `inputs`/`outputs` at all?"
    They're what makes a task a *step*. They also let Pixi cache: run the batch
    again and `ffmpeg` won't re-encode a file whose `_small.mp4` is already current.
    A task with neither is treated as a helper and hidden from the DAG.

---

**Next:** [Two steps, wired by files](two-steps.md) — add a second step and watch
the dependency edge appear on its own.
