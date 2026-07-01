# Writing a pipeline

A Pixiline pipeline is an ordinary [Pixi](https://pixi.sh) workspace. There's no
`config.yaml`, no plugin, and no wrapper framework to learn — you write Pixi
**tasks**, and Pixiline reads them.

This section builds a pipeline up from a single task to a branching,
multi-environment one, adding **one idea at a time**. Read it in order, or jump to
the example that matches what you need:

<div class="grid cards" markdown>

- **[A single step](single-step.md)** — the smallest useful pipeline: one task
  that reads the user's file and writes one output.
- **[Two steps, wired by files](two-steps.md)** — make one step read another's
  output, and the DAG edge appears automatically.
- **[Tunable settings](settings.md)** — turn task args into the Settings form,
  with defaults and dropdowns.
- **[External scripts & environments](external-scripts.md)** — move work into
  script files and give heavy steps their own environment.
- **[A branching pipeline](branching.md)** — one step feeds two parallel analyses
  that merge before a final step: a diamond graph.

</div>

## Anatomy of a step

A **step** is a `[tasks.<name>]` that declares `inputs` and/or `outputs`. Three
things turn a plain task into a Pixiline step:

`args`
: The task's arguments. Pixiline treats three names specially — the **run
  identity** it fills in for you:

    | Arg        | Pixiline supplies…                                   |
    | ---------- | ---------------------------------------------------- |
    | `input`    | the path of the file being processed                 |
    | `output`   | the Destination folder you chose                     |
    | `stem`     | the input file's name without its extension          |

    Any **other** arg is a tunable **[setting](../inputs.md#settings)**: give it a
    `default` (and optionally `choices`) and it shows up in the Settings form.

`inputs` / `outputs`
: Globs describing what the step reads and writes. They do double duty: they
  **wire the graph** (see below) and they drive **Pixi's up-to-date caching**.

`description`
: A sentence shown when the step is focused in the DAG.

### Templating

Inside `cmd`, `inputs`, and `outputs`, refer to any arg with `{{ name }}`:

```toml
cmd = "process {{ input }} --out {{ output }}/{{ stem }}.csv"
outputs = ["{{ output }}/{{ stem }}.csv"]
```

Pixiline substitutes the run identity (`{{ input }}`, `{{ output }}`, `{{ stem }}`)
and your settings before invoking `pixi run`. At run time the step becomes a plain
command like:

```bash
pixi run -e <env> <task> <arg values…>
```

### How steps connect

Pixiline draws an edge **A → B** when one of A's `outputs` supplies one of B's
`inputs`. You never declare edges — you just make step B read a file step A writes.
A step's inputs can come from three places:

1. the **user file** — `{{ input }}` (a fresh file each run);
2. an **artifact from an earlier step** — this is what creates a DAG edge;
3. a **static file already on disk** — a script, a config, a reference dataset (a
   real input for caching, but it adds no edge because no step *produces* it).

You'll meet all three across the examples.

## Troubleshooting checklist

When your pipeline doesn't look the way you expect in Pixiline:

- [ ] Does each step you want shown declare **`inputs` and/or `outputs`**? Tasks
      without them are treated as helpers and hidden.
- [ ] Are your run-identity args named exactly **`input`**, **`output`**, **`stem`**?
      Only those are auto-filled.
- [ ] Do the **producer's `outputs`** and the **consumer's `inputs`** name the same
      path? That's what draws an edge.
- [ ] Is each step under the right **`[feature.<env>.tasks.…]`** so it runs in the
      environment you intend?
- [ ] Are the environments declared in **`[environments]`** so `pixi run -e <env>`
      resolves?

See [Steps & the DAG](../steps.md) and [Inputs, settings & queueing](../inputs.md)
for how these show up in the app.

!!! tip "Ready?"
    Start with **[A single step](single-step.md)**.
