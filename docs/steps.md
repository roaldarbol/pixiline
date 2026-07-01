# Steps & the DAG

The centre of a pipeline's workbench is the **Steps** card — a rendered
**dependency graph (DAG)** of the pipeline. It's the primary way you choose what to
run.

![The Steps DAG](assets/dag-light.png#only-light){ loading=lazy }
![The Steps DAG](assets/dag-dark.png#only-dark){ loading=lazy }

## What a step is

A **step** is a Pixi task that declares `inputs` and/or `outputs`:

- it runs in an **environment** (the Pixi feature it's listed under);
- it has typed **`args`** — the *run identity* (which file, where to write) plus
  tunable **[settings](inputs.md#settings)** with defaults and choices;
- it declares **`inputs`/`outputs`** globs, which both wire the graph and drive
  caching;
- it carries a **`description`**, shown when you click it.

You never write a separate graph file — see
[Writing a pipeline](writing-a-pipeline/index.md) for the manifest side.

## How the graph is derived

Pixiline draws an edge from **step A to step B** when one of A's `outputs` supplies
one of B's `inputs`. Match A's `outputs/tracks.csv` to B's `inputs/tracks.csv` and
you get an arrow A → B. Nodes are laid out left-to-right by dependency depth, so
producers sit to the left of the steps that consume them.

This is why the example pipeline forms a **diamond**: `convert` feeds both `track`
and `pose`, and `analyse` merges them before `report`.

```text
convert ─┬─▶ track ─┐
         └─▶ pose ──┴─▶ analyse ─▶ report
```

## Selecting steps

Each node has a **checkbox** (top-right). Tick it to include the step in the run;
untick it to leave it out. Selected steps are drawn in the accent colour and
connected by solid edges; unselected ones are greyed with dashed edges.

- A **run-order number** appears on the left of each selected node, counting its
  position in the selected chain — it renumbers as you toggle steps.
- **Click a node's body** (anywhere but the checkbox) to *focus* it; its
  description shows beneath the graph.

By default every step is selected, so a fresh pipeline is ready to run end to end.

## Selection is free — run time decides

There's no config-time gating: you can tick any combination of steps. Whether a
step *actually* runs for a given input file is decided at **run time**, Snakemake-
style:

- a step is **skipped for a file** if its inputs aren't available for that file
  (e.g. you selected `analyse` but not the steps that produce its inputs, and
  they're not already on disk);
- a step is **skipped as up-to-date** when Pixi's caching sees its `outputs` are
  already current for its `inputs`.

So you can safely select the whole chain and re-run: Pixiline (via Pixi) does only
the work that's actually needed. More on that in [Jobs & the terminal](jobs.md).
