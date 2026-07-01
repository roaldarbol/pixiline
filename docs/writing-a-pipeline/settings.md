# Tunable settings

So far every arg has been part of the run identity. The moment you give an arg a
**`default`**, it stops being required and becomes a **setting** — a knob Pixiline
renders in the [Settings form](../inputs.md#settings) for whoever runs the pipeline.
Add `choices` and the knob becomes a dropdown instead of a text field.

```toml title="pixi.toml (tasks only)"
[tasks.resize]
description = "Downscale a video, with a chosen height and quality."
args = [
  "input", "output", "stem",
  { arg = "height", default = "720", choices = ["480", "720", "1080"] },  # (1)!
  { arg = "crf",    default = "23" },                                     # (2)!
]
cmd = "ffmpeg -y -i {{ input }} -vf scale=-2:{{ height }} -crf {{ crf }} {{ output }}/{{ stem }}_small.mp4"
inputs = ["{{ input }}"]
outputs = ["{{ output }}/{{ stem }}_small.mp4"]

[tasks.thumbnail]
description = "Grab a poster frame at a chosen timestamp."
args = [
  "output", "stem",
  { arg = "at", default = "0" },                                          # (3)!
]
cmd = "ffmpeg -y -ss {{ at }} -i {{ output }}/{{ stem }}_small.mp4 -frames:v 1 {{ output }}/{{ stem }}_thumb.png"
inputs = ["{{ output }}/{{ stem }}_small.mp4"]
outputs = ["{{ output }}/{{ stem }}_thumb.png"]
```

1. A **dropdown** in Settings — one of `480` / `720` / `1080`, defaulting to `720`.
2. A plain **text field**, defaulting to `23`. Any arg with a default but no
   `choices` renders this way.
3. A second setting, this time on the `thumbnail` step. Settings are **grouped by
   step** in the form, so it's clear which knob belongs where.

## Required vs. tunable, at a glance

The presence of a `default` is the whole distinction:

| Arg form                                        | Role          | Shown in Settings? |
| ----------------------------------------------- | ------------- | ------------------ |
| `"input"` / `"output"` / `"stem"`               | run identity  | no — auto-filled   |
| `{ arg = "crf", default = "23" }`               | setting       | yes — text field   |
| `{ arg = "height", default = "720", choices=…}` | setting       | yes — dropdown     |

## What Pixiline makes of it

The Settings card now shows a **Resize** group (with *Height* and *Crf*) and a
**Thumbnail** group (with *At*). Settings are **pipeline-level**: the values you pick
apply to every input in the batch, so one choice of height re-encodes the whole set
consistently.

Want to compare two settings? Choose a value, **Add to Queue**, change it, and
**Add to Queue** again — each staged job keeps its own snapshot, so the two runs stay
independent even though they share a pipeline.

!!! warning "Settings that appear in a path become part of the cache key"
    If you put a setting inside an `outputs` path — say
    `{{ stem }}_{{ height }}p.mp4` — then each value writes a **distinct file** and
    Pixi caches them separately (so `480` and `1080` can coexist). In the example
    above, `height`/`crf` change the video's *content* but not its *name*, so
    re-running with a new value **overwrites** the previous result. Decide which you
    want, and name the output accordingly.

!!! note "Choices keep runs valid"
    A `choices` list is the easiest way to stop a pipeline being handed a value a
    tool can't accept — the person running it can only pick from the set you allow.

---

**Next:** [External scripts & environments](external-scripts.md) — graduate from
one-line commands to real script files, each with the dependencies it needs.
