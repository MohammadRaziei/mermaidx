# mermaidx documentation

The site at <https://mohammadraziei.github.io/mermaidx/>. It is a [Docusaurus](https://docusaurus.io) site, and
**everything is run through the `Makefile` in the repository root**. You do not need to call `npm`, `node` or
`python` yourself: each target installs what it needs, once, and skips the install while its inputs are unchanged.

## What you need

| Tool | Version | Used for |
| --- | --- | --- |
| GNU `make` | 3.81 or newer (the one macOS ships works) | running everything |
| Python | 3.9 or newer | mermaidx itself, the showcase and the benchmark |
| Node.js | 20 or newer | Docusaurus, and mermaid-cli for the benchmark |

On Windows, use WSL or Git Bash.

## Everyday use

Run these from the repository root.

```bash
make serve        # docs with live reload at http://localhost:3000/mermaidx/
make build        # static site into docs/build
make preview      # build, then serve it the way GitHub Pages will
make benchmark    # render every sample with every renderer (slow, see below)
make all          # benchmark, then build: exactly what CI runs
make clean        # remove generated files, keep installed dependencies
make distclean    # also remove node_modules and the virtualenv
make help         # list every target
```

The first run of any target is slower because it installs dependencies. After that, `make build` only builds.

### What gets installed, and where

| What | Where | Re-installed when |
| --- | --- | --- |
| Python packages (mermaidx with every backend) | a virtualenv in `.cache/venv` | `pyproject.toml` changes |
| Docusaurus and the site's npm packages | `docs/node_modules` | `docs/package.json` or `package-lock.json` changes |
| mermaid-cli (`mmdc`), for the benchmark only | `.cache/mmdc` | never, unless you `make distclean` |

Nothing is installed globally and the system Python is never touched.

## What is generated, and what is not

Generated files are ignored by git, so they are never committed. CI builds them.

| File | Made by | Source |
| --- | --- | --- |
| `docs/src/data/showcase.json` and `docs/static/img/showcase/*.png` | `make showcase` | `docs/scripts/make_showcase.py` and `tests/samples/*.mmd` |
| `docs/static/benchmarks/results.json` and `png/` | `make benchmark` | `benchmarks/run.py` and `tests/samples/*.mmd` |
| `docs/docs/architecture.md` and `changelog.md` | `docs/scripts/sync.js` | `architecture.md` and `CHANGELOG.md` in the repository root |

`make build` and `make serve` create the showcase and the synced pages when they are missing or out of date. They do
not run the benchmark, so the benchmark page shows a notice until you run `make benchmark`.

## Layout

```
Makefile                      the only entry point
benchmarks/run.py             renders every sample and records the time
docs/
  docs/                       the documentation pages (Markdown)
  src/pages/index.js          landing page
  src/pages/benchmarks.js     benchmark gallery
  src/components/             Showcase (rotating examples) and BenchCharts (chart.js)
  src/css/custom.css          colors and fonts, light and dark
  scripts/make_showcase.py    renders the landing-page examples with mermaidx
  scripts/sync.js             copies architecture.md and CHANGELOG.md in
  static/img/                 logo and favicon
  sidebars.js                 order of the pages in the sidebar
  docusaurus.config.js        site configuration
```

## Common tasks

**Edit or add a page.** Change a file in `docs/docs/`, or add a new one and list its name in `docs/sidebars.js`.
Run `make serve` to see it. The pages `architecture` and `changelog` are copies: edit `architecture.md` or
`CHANGELOG.md` in the repository root instead.

**Change the examples on the landing page.** Edit the `SLIDES` list at the top of `docs/scripts/make_showcase.py`.
Each entry is a sample name from `tests/samples` and a tab label. Pick diagrams that are roughly as wide as they are
tall, because very wide or very tall ones become small in the fixed-size panel. Then run `make showcase`, or just
`make serve`, which does it when the script has changed.

**Run the benchmark.**

```bash
make benchmark                                   # every sample, every renderer
make benchmark WITH_MMDC=0                       # without mermaid-cli, no Chromium download
make benchmark BENCH_ARGS="--only 31_venn --repeats 10"
```

It renders each file in `tests/samples` with mermaid-cli and with each mermaidx backend, then writes
`results.json` and the PNGs for the benchmark page. Run `make serve` afterwards to look at them.
`BENCH_ARGS` is passed to `benchmarks/run.py`; see `python benchmarks/run.py --help` inside the virtualenv, or the
page [How the benchmarks work](docs/benchmarks-method.md).

The first `make benchmark` with mermaid-cli downloads about 170 MB of Chromium. `NO_SANDBOX=1` makes Chrome start
as root or inside a container, and CI sets it.

**Add a sample.** Put a `.mmd` file in `tests/samples`. It shows up in the benchmark and in the structural tests.

## How CI works

`.github/workflows/docs.yml` checks out the repository, sets up Python and Node.js, and runs `make all` with
`NO_SANDBOX=1`. The result in `docs/build` is published to GitHub Pages. Pull requests run the same build and skip
the deploy.

One-time setup on GitHub: **Settings, Pages, Source: GitHub Actions**.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `error: 'node' is required` | Install Node.js 20 or newer. |
| `make benchmark` fails while installing mermaid-cli | Chromium could not be downloaded. Use `make benchmark WITH_MMDC=0`, or fix the network. |
| `mmdc` renders nothing on a server or in a container | Add `NO_SANDBOX=1`. |
| The benchmark page says there are no results | Run `make benchmark`, then `make serve`. |
| The build fails after changing `package.json` | Run `make build` again: the dependencies are reinstalled when that file changes. If it still fails, `make distclean`. |
| `make` says a file is up to date but looks wrong | `make clean`, then run the target again. |
