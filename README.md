# Audio Visualizer

## Hardware

A graphical EQ display, based on a dsPIC33AK256MPS103 digital signal controller.

## Continuous integration

GitHub Actions checks every KiCad project under `hdw/` automatically (`.github/workflows/hardware.yml`):

| Job | What it does |
|---|---|
| Repo hygiene | Fails on committed backups, lock files or caches, and on files not saved by KiCad 10.0. Checks that each project's schematic PDF (`<project>.pdf`) is committed and was re-plotted after the last schematic change. |
| ERC / DRC / libraries | Runs ERC, and DRC with schematic parity. Also checks that every symbol and footprint library resolves on a clean machine (project lib tables must use `${KIPRJMOD}`). For projects with a project library, checks that every placed symbol, footprint and 3D model comes from it. |
| Visual diff | On every run, renders changed schematic pages and PCB layers against the previous commit or PR base (red = removed, green = added). |

Per-project settings live in `hdw/ci-config.json`. Each of `erc`, `drc`, `libraries`, `project_lib` and `pdf` is `enforce` (fail the build), `report` (annotate only) or `off`. `project_lib` also needs `project_lib_dir` (relative to the project folder, e.g. `"../../../project_lib"`): the lib tables may only point into that folder, every placed symbol and board footprint (and every symbol's Footprint field) must exist in those libraries, and every 3D model path must resolve to a file inside it. ERC/DRC items excluded in KiCad are not counted. Personal libraries that aren't in this repo are listed under `external_libraries` and cloned by CI under the same nicknames.

To run the checks locally:

```sh
KICAD_CLI="C:/Program Files/KiCad/10.0/bin/kicad-cli.exe" python tools/ci/kicad_ci.py check hdw/DSP_board/rev_a/Audio_Visualiser_DSP
python tools/ci/kicad_ci.py hygiene
```

Fab outputs (schematic/PCB PDFs, Gerbers + drill, IPC-D-356, BOM, pick-and-place, STEP and renders) are built manually:

```sh
python tools/ci/kicad_ci.py outputs hdw/DSP_board/rev_a/Audio_Visualiser_DSP --out fab-out --label <version>
```
