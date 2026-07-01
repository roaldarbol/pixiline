# External scripts & environments

Real steps rarely fit on one `cmd` line, and they rarely share a dependency stack. A
detector wants PyTorch; a report wants pandas; a transcode wants ffmpeg. Pixi lets
each step run in its **own environment**, and there's nothing stopping a step from
calling an **external script file** instead of an inline command.

This example resizes a video (as before) and then runs an object detector that lives
in `scripts/detect.py`, in an environment of its own:

```toml title="pixi.toml"
[workspace]
name = "detect-pipeline"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64", "win-64"]

[dependencies]
ffmpeg = ">=6"

# A separate environment just for the detector's heavy stack.
[feature.detect.dependencies]
python = ">=3.11"
pytorch = ">=2"

[tasks.resize]
description = "Downscale a video to 720p."
args = ["input", "output", "stem"]
cmd = "ffmpeg -y -i {{ input }} -vf scale=-2:720 {{ output }}/{{ stem }}_small.mp4"
inputs = ["{{ input }}"]
outputs = ["{{ output }}/{{ stem }}_small.mp4"]

[feature.detect.tasks.detect]                                          # (1)!
description = "Run object detection over the downscaled video."
args = [
  "output", "stem",
  { arg = "model", default = "yolo11n", choices = ["yolo11n", "yolo11s", "yolo11m"] },
]
cmd = "python scripts/detect.py {{ output }}/{{ stem }}_small.mp4 {{ output }}/{{ stem }}_boxes.json --model {{ model }}"
inputs = [
  "{{ output }}/{{ stem }}_small.mp4",   # (2)!
  "scripts/detect.py",                   # (3)!
]
outputs = ["{{ output }}/{{ stem }}_boxes.json"]

[environments]
default = { solve-group = "default" }
detect = ["detect"]                                                    # (4)!
```

1. The step is declared under **`[feature.detect.tasks.detect]`**, so it belongs to
   the `detect` feature — and Pixiline runs it in the matching environment.
2. The artifact from `resize` — this wires the edge `resize → detect`.
3. The **script itself**, listed as a static input. It produces no edge (no step
   *makes* `detect.py`), but it *does* join the cache key.
4. The `detect` environment is declared here so `pixi run -e detect …` resolves.

## Environments: one step, one stack

Because `detect` lives under `[feature.detect.…]`, Pixiline launches it as:

```bash
pixi run -e detect detect <output> <stem> <model>
```

while `resize` runs in the default environment. Different steps in the **same
pipeline** can use completely different environments — that's the whole point of
keeping the detector's PyTorch out of the lightweight transcode step. Pixiline reads
which environment each step belongs to straight from the manifest; you don't
configure anything on its side.

## External files as inputs

Listing `scripts/detect.py` in `inputs` is a small move with a big payoff. Pixi's
caching now watches the script:

- edit `scripts/detect.py` and re-run → `detect` re-runs (your change takes effect);
- leave it alone → `detect` is skipped as up-to-date.

The same trick works for **any** file a step depends on — a weights file, a
calibration table, a shared config. If the result depends on it, list it in
`inputs`, and Pixi will do the right thing. The only inputs that create **edges** are
the ones another step *produces*; everything else is just a dependency for caching.

!!! tip "Keep scripts in the workspace"
    Put step scripts under the pipeline folder (e.g. `scripts/`) and reference them
    by relative path. They travel with the `pixi.toml`, stay under version control,
    and their paths resolve the same for everyone who runs the pipeline.

---

**Next:** [A branching pipeline](branching.md) — put it all together into the
diamond graph you've seen throughout these docs.
