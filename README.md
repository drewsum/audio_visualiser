# Audio Visualizer

## Hardware

A graphical EQ display, based on a dsPIC33AK256MPS103 digital signal controller.

## Continuous integration

GitHub Actions checks every KiCad project under `hdw/` automatically (`.github/workflows/hardware*.yml`):

| Job | What it does |
|---|---|
| Repo hygiene | Fails on committed backups, lock files or caches, and on files not saved by KiCad 10.0. Checks that each project's schematic PDF (`<project>.pdf`) is committed and was re-plotted after the last schematic change. |
| ERC / DRC / libraries | Runs ERC, and DRC with schematic parity. Also checks that every symbol and footprint library resolves on a clean machine (project lib tables must use `${KIPRJMOD}`). |
| Fab outputs | Builds schematic/PCB PDFs, Gerbers + drill, IPC-D-356, BOM, pick-and-place, STEP and renders as a downloadable artifact. |
| Release | Pushing a tag starting with `hw-` (e.g. `hw-dsp-rev_a-v1`) publishes those outputs as a GitHub release. |
| Visual diff | On PRs, renders changed schematic pages and PCB layers (red = removed, green = added). |

Per-project settings live in `hdw/ci-config.json`. Each of `erc`, `drc`, `libraries` and `pdf` is `enforce` (fail the build), `report` (annotate only) or `off`. Personal libraries that aren't in this repo are listed under `external_libraries` and cloned by CI under the same nicknames.

To run the checks locally:

```sh
KICAD_CLI="C:/Program Files/KiCad/10.0/bin/kicad-cli.exe" python tools/ci/kicad_ci.py check hdw/DSP_board/rev_a/Audio_Visualiser_DSP
python tools/ci/kicad_ci.py hygiene
```
