# FAQ

## Is Pixiline an official Pixi / Prefix.dev product?

**No.** Pixiline is an independent, community-built, MIT-licensed tool. It is **not
affiliated with, endorsed by, or supported by** the [Pixi](https://pixi.sh) project
or [Prefix.dev](https://prefix.dev). It simply *uses* Pixi to run your pipelines.
"Pixi" and its logo belong to their respective owners; the Pixi-inspired colour
scheme in these docs is an homage, not a claim of association.

## Does Pixiline modify my `pixi.toml`?

No. Pixiline only **reads** your manifest (via `pixi task list`) and **runs** tasks
(via `pixi run`). Your `pixi.toml` is the single source of truth and is never
written to.

## Why doesn't my task show up as a step?

Pixiline treats a task as a **step** only if it declares **`inputs` and/or
`outputs`**. Tasks without them (a `lint`, a `gui`, a one-off helper) and hidden
tasks (names starting with `_`) are deliberately excluded. See
[Writing a pipeline](writing-a-pipeline/index.md#anatomy-of-a-step).

## Where do my outputs go?

Under the **Destination** folder you pick in the workbench — that's the value of
`{{ output }}` for every step. The layout *within* it is up to your tasks; a common
pattern is a subfolder per input, `{{ output }}/{{ stem }}/…`. See
[Inputs, settings & queueing](inputs.md#destination).

## How does Pixiline decide the run order?

From the graph: it topologically sorts the steps using the edges derived from
`outputs` → `inputs`. Within a job, steps run in that order; the run-order numbers on
the DAG show the sequence for the steps you've selected.

## What happens if I select a step whose inputs aren't ready?

Nothing breaks — Pixiline gates at **run time**. A step is skipped for a given file
if its inputs aren't available (not produced by an earlier selected step and not
already on disk). See
[Steps & the DAG](steps.md#selection-is-free-run-time-decides).

## Does it re-run work that's already done?

Only what's needed. Because steps declare `inputs`/`outputs`, Pixiline relies on
**Pixi's up-to-date caching** to skip steps whose outputs are already current. Re-run
a batch after adding one file and the already-processed files do almost nothing.

## Can I run several pipelines at once?

Yes. Load as many pipelines as you like; they all feed the **same** Jobs queue.
Whether jobs run one-at-a-time or several at once is controlled by the **Parallel**
toggle on the [Jobs view](jobs.md#parallel).

## Can I cancel a run cleanly?

Yes. **Cancel** kills the **entire process tree** for that job, so no `pixi` or child
processes are left orphaned. Closing the app cancels running jobs for the same
reason.

## Does Pixiline need a GPU / torch / R / …?

No. Pixiline carries **no pipeline dependencies of its own** — it's a small PySide6
app. Each pipeline brings its own Pixi environments (torch, R, whatever), and
Pixiline runs them via `pixi`.

## Which platforms are supported?

Pixiline is developed and packaged for **Windows and Linux**; because it's plain
PySide6 + Pixi it should run anywhere Pixi and Qt do. See
[Installation](quickstart/installation.md).
