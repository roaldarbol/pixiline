# Inputs, settings & queueing

Once you've [picked the steps](steps.md), the rest of the workbench is about *what*
to run them on and *how*, then staging the work. Three things make up a run:

1. a **Destination** (where outputs go),
2. the **Settings** (the tunable knobs), and
3. the **Inputs** (the files to process).

![The workbench: destination, settings, inputs](assets/app-pipeline-light.png#only-light){ loading=lazy }
![The workbench: destination, settings, inputs](assets/app-pipeline-dark.png#only-dark){ loading=lazy }

## Destination

The **Destination** field at the top sets the output base directory — the
`{{ output }}` every step writes under. Click the field (or **Browse…**) to pick a
folder. It's remembered between sessions, so you usually set it once.

Each pipeline's steps decide the layout *within* that folder (commonly
`{{ output }}/{{ stem }}/…`, i.e. a subfolder per input file). See
[Writing a pipeline](writing-a-pipeline/index.md#templating) for the templating.

## Settings

The **Settings** card is generated automatically from each step's tunable `args` —
the ones that declare a **`default`** (and optionally a set of **`choices`**). An
arg with choices becomes a dropdown; a plain one becomes a text field.

- Settings are **pipeline-level**: they apply to every input you queue for this
  pipeline, so the same knobs are used across the batch.
- Steps that expose no tunable args simply don't appear here; a pipeline with no
  settings at all shows a short note instead.

You don't write any form code — declare the args in your `pixi.toml` and the form
appears. That's the whole
[settings mechanism](writing-a-pipeline/settings.md).

!!! note "Run-identity args aren't settings"
    Args with **no** default — typically `input`, `output`, and `stem` — are the
    *run identity*. Pixiline fills those in for you from the Destination and each
    input file, so they don't clutter the Settings form.

## Inputs

The **Inputs** list on the right is the batch of files to run the pipeline on:

- **Add files…** to browse, or **drag files** straight onto the list.
- **Remove** drops the selected file.

Each file becomes one **job** — the whole selected step-chain, run for that file.
Ten files and five steps means ten jobs, each doing up to five steps.

## Add to Queue

When you have a destination, at least one step, and at least one input, the
**Add to Queue** button lights up. Click it to **stage** one job per input file on
the [Jobs view](jobs.md); a short confirmation flashes so you know it landed.

Staging doesn't start anything — it collects the work. Head to the **Jobs** view to
run it. Because every pipeline feeds the same queue, you can stage from several
pipelines and run them together.

!!! tip "Queue the same file twice"
    Want to compare two settings? Set the knobs, **Add to Queue**, change a setting,
    and **Add to Queue** again. Each staged job carries its own snapshot of the
    settings, so the two runs stay independent.
