# Jobs & the terminal

The **Jobs** view is the single, app-wide queue and monitor. Everything you stage
from any pipeline's **Add to Queue** lands here, grouped by state, with a live
terminal below.

![The Jobs view](assets/app-jobs-light.png#only-light){ loading=lazy }
![The Jobs view](assets/app-jobs-dark.png#only-dark){ loading=lazy }

## The four groups

Jobs move top-to-bottom through four sections as they run:

- **Queued** — staged, not yet released.
- **Pending** — released and waiting for a free worker slot.
- **Running** — executing now, with a live progress bar and the current step.
- **Finished** — done, failed, or canceled.

Each row shows the pipeline and input name, a **step count** tag (hover it for the
full step chain), a progress bar (measured in *completed steps*), and a status.

## Starting jobs

- **Start all** releases every queued job.
- **Start selected** releases just the rows you've ticked.

Releasing a job doesn't guarantee it runs *immediately* — it enters **Pending** and
starts when a worker slot is free.

### Parallel

By default Pixiline runs **one job at a time**. Many pipelines have GPU- or
IO-bound steps that would contend if run at once, so this is the safe default. Flip
**Parallel (up to N)** on to run several concurrently — the suggested worker count
is based on your machine.

## Watching a run

Click any job (running or not) to show its output in the **terminal** below. The
terminal is a real emulator:

- **ANSI colour** renders as colour, and **in-place progress** (carriage returns)
  updates one line instead of scrolling thousands.
- It follows the app's light/dark theme.
- A running job streams into it live; clicking a finished job replays its captured
  output.

## Logs on disk

Nothing is lost when you close the terminal — every run is also written to disk:

- **A per-run log** lands next to the outputs, at
  `<destination>/<stem>/logs/<timestamp>.log`. It's a **settled, plain-text** copy
  of the run: ANSI colour is stripped and in-place progress bars are collapsed to
  their final values, so it's one tidy line per step instead of thousands of
  redraws. It's flushed as the run goes (so it survives even if a step crashes) and
  timestamped, so a later re-run never overwrites an earlier one.
- **A session log** for Pixiline itself lands in
  `~/.pixiline/logs/pixiline-<timestamp>.log` — job/step events, errors, and a full
  traceback if the app ever hits an uncaught exception.

So a finished batch leaves a clean, per-recording record you can read, diff, or
attach to a bug report long after the window is closed.

## Stopping & tidying

- **Cancel** stops a running job — Pixiline kills the **whole process tree**, so no
  `pixi`/child processes are left orphaned. On a queued or pending job, Cancel just
  drops it.
- **Remove selected** removes staged rows you've ticked (running jobs are left
  alone).
- **Clear finished** tidies away everything in the Finished group.

The slim **status strip** at the very bottom of the window mirrors the counts and
overall progress, so you can leave the Jobs view and still see how the batch is
doing.

## Skipping work that's already done

Because each step declares `inputs`/`outputs`, Pixiline leans on **Pixi's up-to-date
caching**: when a step's outputs are already current for its inputs, Pixi skips it.
Re-running a batch after adding one new file therefore does mostly nothing for the
files that are already processed — only the new (or changed) work runs. See
[Steps & the DAG](steps.md#selection-is-free-run-time-decides) for how run-time
gating and caching combine.
