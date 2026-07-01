# Credits

Pixiline is built and maintained by **Mikkel Roald-Arbøl** and
[contributors](https://github.com/roaldarbol/pixiline/graphs/contributors), and
released under the **MIT License**.

## Not affiliated with Pixi / Prefix.dev

Pixiline is an **independent, community project**. It is **not affiliated with,
endorsed by, or supported by** [Prefix.dev](https://prefix.dev) or the
[Pixi](https://pixi.sh) project. Pixiline *uses* Pixi as its execution engine, and
these docs borrow a Pixi-inspired colour palette as a friendly nod — but "Pixi", the
Pixi name, and the Pixi logo belong to their respective owners, and nothing here
should be read as an official association.

If you're looking for Pixi itself, head to **[pixi.sh](https://pixi.sh)**.

## Built with

- **[Pixi](https://pixi.sh)** — the workspace & task runner Pixiline drives.
- **[PySide6 / Qt](https://doc.qt.io/qtforpython/)** — the GUI toolkit.
- **[pyte](https://github.com/selectel/pyte)** — the terminal emulator behind the
  live log.
- **[loguru](https://github.com/Delgan/loguru)** — session logging.
- **[Zensical](https://zensical.org)** — the static-site generator these docs are
  built with (from the makers of Material for MkDocs).
- **[Ruff](https://github.com/astral-sh/ruff)** — linting & formatting.

## Contributing

The codebase is small and meant to stay readable. Issues and pull requests are
welcome at
[github.com/roaldarbol/pixiline](https://github.com/roaldarbol/pixiline).

To work on the docs specifically:

```bash
pixi run docs          # serve locally with live reload
pixi run docs-build    # build the static site into ./site/
pixi run screenshots   # regenerate the light/dark screenshots
```

## License

MIT — see [LICENSE](https://github.com/roaldarbol/pixiline/blob/main/LICENSE).
