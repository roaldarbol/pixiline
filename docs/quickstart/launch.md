# Launch

<p align="center" markdown>
  ![Pixiline app icon](../assets/launch-icon-light.png#only-light){ width="160" }
  ![Pixiline app icon](../assets/launch-icon-dark.png#only-dark){ width="160" }
</p>

Once [installed](installation.md), launch **Pixiline** like any other app — look for
this icon. It registers itself in the usual places:

- **Windows** — the **Start menu** (and a desktop shortcut)
- **Linux** — your application menu

Prefer the terminal? It's also a command:

```bash
pixiline   # opens with no pipeline loaded
```

Pixiline opens on the **Pipelines** view with an empty drop screen:

![The empty drop screen](../assets/app-drop-light.png#only-light){ loading=lazy }
![The empty drop screen](../assets/app-drop-dark.png#only-dark){ loading=lazy }

From here, [load a pipeline](../loading.md) by dropping a `pixi.toml` onto the window.

!!! tip "Light or dark"
    Pixiline follows your system light/dark theme automatically — every panel, the
    DAG, and the terminal recolour live when you switch.
