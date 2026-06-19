# Portia sleep pipeline

A self-contained [Pixi](https://pixi.sh) workspace that takes an **original video**
of a *Portia fimbriata* and produces a **final anievent CSV** of classified
sleep behaviour. It is the deployable, apply-only counterpart to the research
notebook `../scripts/rstats/segmentation.qmd`: that notebook *trains and
evaluates* the models; this folder *applies* the already-trained models to new
recordings.

## What it does

```
original video
   │  motion      (BehaveAI)         motion-colour video
   ▼  predict     (Octron + YOLO)    masks + tracking
   ▼  export      (Octron)           per-frame region-property CSV
   ▼  preprocess  (R)                aniframe parquet  (frame index → seconds)
   ▼  segment     (R)                ── FINAL anievent CSV ──
   ▼                                 sleep/wake + Awake/REM/uncertain bouts
```

Sleep vs wake is **unsupervised** (changepoints + 2-means, computed fresh per
recording). The Awake-vs-REM call on each active bout is **supervised**, using the
trained classifier in `models/awake_classifier.rds`.

## Quick start

```sh
# put your recording in data/videos/ (and, ideally, its per-frame timestamp
# CSV in data/timestamps/ — see "Timestamps" below), then:
pixi run process myclip.mp4
```

Everything for the recording lands under `data/output/<stem>/`. The final files
are in `segments/`.

## Outputs (the GUI tick-boxes)

Each step writes a distinct artefact under `data/output/<stem>/`, and each step is
individually runnable — this is what the planned GUI's tick-boxes map onto. From
intermediate → final:

| Tick-box / step | Output artefact | Kind |
|---|---|---|
| `motion`     | `videos/motion/<stem>_motion.mp4`              | intermediate |
| `predict`    | `tracking/raw/<stem>_bytetrack/predictions.zarr` | intermediate |
| `render`     | `videos/tracklets/…` (overlay video)           | optional QC |
| `export`     | `tracking/raw/<stem>_bytetrack/<stem>.csv`     | intermediate |
| `preprocess` | `tracking/processed/<stem>.parquet` (aniframe) | intermediate |
| `segment`    | `segments/<stem>_sleepwake.csv`                | **final** — sleep/wake anievent |
| `segment`    | `segments/<stem>_bouts.csv`                    | **final** — classified bouts + features (the headline anievent) |

`render` is off by default (visual QC only). Select steps explicitly with
`--steps`, or run all-but-some with `--skip`:

```sh
pixi run process myclip.mp4 --steps motion,predict,export   # stop at the CSV export
pixi run process myclip.mp4 --skip render                   # the default chain
pixi run -e tracking predict myclip.mp4                     # just re-run one step
pixi run -e segmentation segment data/output --overwrite    # re-segment everything
```

## Configuration

All settings for **every** step live in [`config.yaml`](config.yaml), organised by
step (`motion`, `predict`, `render`, `export`, `preprocess`, `segment`) — model to
use, region properties to export, changepoint penalty, bout-detector thresholds,
classifier cutoff, etc. One recording is reproducible from this one file. The R and
nushell steps both read it, so there is a single source of truth.

## Environments

Environments are named for the pipeline **stage** they serve, not the tools in
them (the video stages need conflicting Python stacks, so each is separate):

- **default** — orchestration only: nushell to drive the chain + ffmpeg for the FPS probe.
- **motion** — PyTorch + Ultralytics + BehaveAI, for `motion`.
- **tracking** — Octron, for `predict` / `render`.
- **export** — Octron (export branch), for `export`.
- **segmentation** — isolated `r-base` + the `animovement` stack, for `preprocess` / `segment`.
- **gui** — thin PyQt6 front-end (see below).

Channels: `conda-forge`, `https://prefix.dev/animovement` (the `animovement`
package stack), and `https://prefix.dev/isolated-r` (an `r-base` that installs into
a fully isolated prefix — no user/site library leakage).

## Frame timing

Octron numbers frames by **index** and drops frames with no detection, so a row's
real time must be looked up by frame index, not row position. `preprocess.R` builds
the seconds-since-start `time` column from one of two sources:

1. **Per-frame timestamp CSV** in `data/timestamps/<recording_id>.csv` (one
   ISO-8601 timestamp per video frame; `<recording_id>` is the video stem without a
   trailing `_compressed`). The exact path, and preferred.
2. **Probed frame rate** — when no timestamp file exists, `preprocess.R` probes the
   source video's average frame rate with `ffprobe` (`scripts/probe_fps.nu` does the
   same by hand) and maps `time = frame_index / fps`; `start_datetime` is taken from
   the video file's mtime. If neither a timestamp file nor a probeable video is
   found, preprocessing **errors out** rather than guessing — there is no static
   fallback rate.

Downstream, the **sampling rate is never hard-coded**: `segment.R` derives it per
recording from the median interval of the `time` column (robust to dropped frames),
so all time-based parameters in `config.yaml` are given in **seconds** and scaled by
the real rate at run time.

## Models shipped

- `models/yolo-portia/yolo26m_seg_1280_20260327/` — **inference weights only**
  (`weights/best.pt` + `args.yaml`); the training data and epoch checkpoints from
  the full 3.8 GB model are not included.
  - ⚠️ **Stale path in `args.yaml`.** Its `model:` field still points at the base
    checkpoint inside a training-time pixi env
    (`C:\pixi-envs\...\envs\octron\...\yolo26m-seg.pt`) that does not exist here.
    `predict.nu` passes the model *directory* via `--model`, so Octron should load
    `weights/best.pt` and ignore this field — but confirm prediction works (or blank
    that field) before trusting it, since stale absolute paths are a common loader
    trip-up.
- `models/awake_classifier.rds` — the trained Awake-vs-REM workflow.

## Known gap: the classifier threshold

`segmentation.qmd` *tunes* the decision threshold at run time (`tune_threshold()`)
and saves **only** `awake_classifier.rds`, not the threshold. For reproducible
application this pipeline reads `segment.awake_threshold` and `segment.reject_band`
from `config.yaml`, currently set to documented defaults (`0.5` / `0.10`). **To
match the notebook exactly, copy its tuned `thr$best$threshold` into
`config.yaml`** — ideally by having the notebook write it there when it trains the
model.

## Notes for building the GUI

> **For the next LLM/developer building the GUI.** A `gui` Pixi environment already
> exists (`[feature.gui]` in `pixi.toml`: PyQt6 + pyyaml). Run it with
> `pixi run gui` once you create `scripts/gui.py`. Read this before designing it.

**Architecture — the GUI is a thin front-end, nothing more.** It must **not** import
`torch`, `octron`, `animovement`, or call R directly. It orchestrates the pipeline
by **shelling out to `pixi run …`**, exactly like [`scripts/run.nu`](scripts/run.nu)
does. Pixi — not Qt — is what ships and isolates nushell, R, ffmpeg, and the
conflicting Python stacks. The GUI process stays tiny and never touches them.

**What the GUI actually drives:**

- **The tick-boxes are the pipeline steps** (`motion`, `predict`, `render`,
  `export`, `preprocess`, `segment`). They map 1:1 onto the `--steps`/`--skip` list
  that `run.nu` already accepts. So the GUI is essentially a visual builder for one
  command, e.g. `pixi run process clip.mp4 --steps motion,predict,export`. Either
  call `process` with the assembled step list, or invoke each step task directly
  (`pixi run -e motion motion …`, `pixi run -e segmentation preprocess`, `pixi run -e segmentation segment`).
- **Settings come from [`config.yaml`](config.yaml)**, organised per step. The GUI
  should load it (pyyaml), expose the fields, and write it back — it is the single
  source of truth for every step (model, region properties, thresholds, …). Don't
  duplicate settings into the GUI; round-trip the YAML.
- **Outputs / artefacts** land under `data/output/<stem>/` (see the table above).
  The GUI can let the user pick which artefacts to (re)build via the same tick-boxes
  and browse the per-recording output folder when done.

**Implementation guidance:**

- Use **`QProcess`** (not `subprocess` + threads) to launch `pixi run …`: it's
  Qt-native, plays nicely with the event loop, and streams stdout line-by-line. The
  step scripts print `--- Step: <name> ---` / `=== Done ===` markers and cli
  progress lines you can parse to drive per-step progress + checkmarks and a log
  pane.
- Each `pixi run` re-activates its environment (small per-step startup cost);
  negligible for batch use. Don't try to keep long-lived worker processes at first.
- **Distribution: use `pixi-pack`**, not PyInstaller — PyInstaller cannot sanely
  bundle CUDA/torch/R. `pixi-pack` produces a portable, offline-installable archive
  of the whole locked workspace (all environments, models included). For dev use,
  `git clone` + `pixi install` is enough.
- The GUI is intended to live in a **separate repository** eventually; keep it
  decoupled (it only needs to know the task names, the `config.yaml` schema, and the
  `data/output/<stem>/` layout — all documented here).

## R dependencies

The R steps need a handful of CRAN packages (tidyverse, tidychangepoint, tidyclust,
tidymodels, ranger, fastcpd, arrow, vroom, yaml, here), declared as `r-*` packages
in `pixi.toml`. If any are not yet available on conda-forge / the configured
channels under those names, either add them to your channel or fall back to `renv`
for that package. (The parent project currently manages CRAN deps with renv.)
