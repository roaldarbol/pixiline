# A branching pipeline

Everything so far has been a straight line. Real analyses **branch and merge**: one
preparation step feeds several independent analyses, whose results are later combined.
Pixiline handles this the same way it handles a straight chain — by matching `outputs`
to `inputs` — the graph simply stops being a line and becomes a **diamond**.

This example prepares a recording once, analyses it two ways in parallel, then merges
the two results before a final report:

```toml title="pixi.toml"
[workspace]
name = "behaviour-pipeline"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64", "win-64"]

[dependencies]
python = ">=3.11"
ffmpeg = ">=6"

# --- step 1: normalise the recording ---------------------------------------
[tasks.convert]
description = "Transcode the raw recording to a normalised MP4."
args = ["input", "output", "stem", { arg = "fps", default = "30" }]
cmd = "ffmpeg -y -r {{ fps }} -i {{ input }} {{ output }}/{{ stem }}/raw.mp4"
inputs = ["{{ input }}"]
outputs = ["{{ output }}/{{ stem }}/raw.mp4"]                            # (1)!

# --- steps 2 & 3: two analyses, each reading raw.mp4 -----------------------
[tasks.track]
description = "Multi-animal tracking — one row per animal per frame."
args = [
  "output", "stem",
  { arg = "tracker", default = "bytetrack", choices = ["bytetrack", "botsort"] },
]
cmd = "python scripts/track.py {{ output }}/{{ stem }}/raw.mp4 {{ output }}/{{ stem }}/tracks.csv --tracker {{ tracker }}"
inputs = ["{{ output }}/{{ stem }}/raw.mp4"]                             # (2)!
outputs = ["{{ output }}/{{ stem }}/tracks.csv"]

[tasks.pose]
description = "Pose estimation — body-part keypoints for every frame."
args = [
  "output", "stem",
  { arg = "model", default = "hrnet", choices = ["hrnet", "resnet50", "vitpose"] },
]
cmd = "python scripts/pose.py {{ output }}/{{ stem }}/raw.mp4 {{ output }}/{{ stem }}/pose.h5 --model {{ model }}"
inputs = ["{{ output }}/{{ stem }}/raw.mp4"]                             # (2)!
outputs = ["{{ output }}/{{ stem }}/pose.h5"]

# --- step 4: merge the two analyses ----------------------------------------
[tasks.analyse]
description = "Combine tracks + pose into per-animal behavioural features."
args = [
  "output", "stem",
  { arg = "smoothing", default = "savgol", choices = ["none", "savgol", "median"] },
]
cmd = "python scripts/analyse.py {{ output }}/{{ stem }} --smoothing {{ smoothing }}"
inputs = [
  "{{ output }}/{{ stem }}/tracks.csv",   # (3)!
  "{{ output }}/{{ stem }}/pose.h5",      # (3)!
]
outputs = ["{{ output }}/{{ stem }}/summary.csv"]

# --- step 5: render a report -----------------------------------------------
[tasks.report]
description = "Render a self-contained HTML report of the run."
args = ["output", "stem"]
cmd = "python scripts/report.py {{ output }}/{{ stem }}/summary.csv {{ output }}/{{ stem }}/report.html"
inputs = ["{{ output }}/{{ stem }}/summary.csv"]
outputs = ["{{ output }}/{{ stem }}/report.html"]
```

1. `convert`'s single output is read by **both** `track` and `pose` — so it has two
   *outgoing* edges. That's the branch.
2. Both analyses read the same `raw.mp4`. Neither knows about the other; they're
   independent.
3. `analyse` reads **two** produced artifacts, so it has **two** *incoming* edges
   (`track → analyse` and `pose → analyse`). That's the merge.

## The shape

Match the `outputs`/`inputs` and the diamond falls out on its own — you never declare
it:

```text
convert ─┬─▶ track ─┐
         └─▶ pose ──┴─▶ analyse ─▶ report
```

![The branching pipeline in Pixiline](../assets/app-pipeline-light.png#only-light){ loading=lazy }
![The branching pipeline in Pixiline](../assets/app-pipeline-dark.png#only-dark){ loading=lazy }

A branch is just **one output feeding several inputs**; a merge is **several outputs
feeding one input**. Chain those and you can express any dependency graph — Pixiline
lays it out left-to-right by depth and runs the steps in topological order.

## What Pixiline makes of it

You've seen it: a five-node diamond, every step selected, the focused step's
description beneath the graph, and a Settings form with the `fps`, `tracker`, `model`,
and `smoothing` knobs grouped by step. Queue a folder of recordings, flip **Parallel**
on if your machine can take it, and watch them flow through the [Jobs view](../jobs.md).

That's the whole model: **the `pixi.toml` is the pipeline.** Everything Pixiline shows
— the DAG, the run order, the Settings form, the caching — is read from tasks you'd
want to write anyway.

!!! tip "Per-file subfolders"
    This pipeline writes into `{{ output }}/{{ stem }}/…` — a **subfolder per input** —
    because each recording produces several files. Grouping them per recording is
    tidier than a flat folder of suffixed names; just have a step `mkdir -p` the
    folder before writing if the tool won't create it.

---

Back to the [overview](index.md), or see [Steps & the DAG](../steps.md) for how this
graph is drawn and selected in the app.
