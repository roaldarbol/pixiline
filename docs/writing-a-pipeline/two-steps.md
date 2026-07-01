# Two steps, wired by files

A pipeline becomes a *pipeline* when one step feeds another. In Pixiline you never
draw that connection by hand — you make the second step **read a file the first step
writes**, and the edge appears in the DAG on its own.

We'll add a `thumbnail` step that grabs a poster frame from the downscaled video:

```toml title="pixi.toml (tasks only)"
[tasks.resize]
description = "Downscale a video to 720p."
args = ["input", "output", "stem"]
cmd = "ffmpeg -y -i {{ input }} -vf scale=-2:720 {{ output }}/{{ stem }}_small.mp4"
inputs = ["{{ input }}"]
outputs = ["{{ output }}/{{ stem }}_small.mp4"]

[tasks.thumbnail]
description = "Grab a poster frame from the downscaled video."
args = ["output", "stem"]                                             # (1)!
cmd = "ffmpeg -y -i {{ output }}/{{ stem }}_small.mp4 -frames:v 1 {{ output }}/{{ stem }}_thumb.png"
inputs = ["{{ output }}/{{ stem }}_small.mp4"]                        # (2)!
outputs = ["{{ output }}/{{ stem }}_thumb.png"]
```

1. `thumbnail` never touches the user's original file, so it declares **only**
   `output` and `stem` — not `input`. A step only asks for the run-identity args it
   actually uses.
2. Its input is the artifact `resize` produced. This single line is what wires the
   edge.

## The edge, and why it points that way

Pixiline compares every step's `outputs` against every other step's `inputs`. Here
`resize.outputs` contains `{{ output }}/{{ stem }}_small.mp4`, and that's exactly
`thumbnail.inputs` — so it draws:

```text
resize ─▶ thumbnail
```

The direction matters: the **producer** (`resize`) must *cover* the **consumer's**
input, not the other way round. That's why naming is worth care — if the two paths
don't match character-for-character (after templating), no edge is drawn and the
steps look unrelated in the DAG.

## What Pixiline makes of it

The DAG now shows two connected boxes, both selected by default. Each input file
becomes one job that runs `resize` then `thumbnail`, in that order — the run-order
numbers on the nodes (**1**, **2**) confirm the sequence.

Because both steps declare `inputs`/`outputs`, Pixi caches each independently:

- change nothing and re-run → both steps are skipped as up-to-date;
- delete a `_thumb.png` and re-run → only `thumbnail` runs again;
- replace a source video → both run again for that file.

!!! note "Untick to run part of the chain"
    You can deselect `resize` and run only `thumbnail` — Pixiline will use whatever
    `_small.mp4` is already on disk. If it isn't there, the step is simply skipped
    for that file at run time (see
    [Steps & the DAG](../steps.md#selection-is-free-run-time-decides)).

---

**Next:** [Tunable settings](settings.md) — expose knobs so the person running
the pipeline can adjust it without touching the `pixi.toml`.
