# 2. Setup

## 2.1 Requirements

| Item | Version / value | Notes |
|---|---|---|
| OS | Linux (tested Ubuntu, kernel 6.x) | |
| GPU | NVIDIA RTX-capable (tested Tesla T4, 15 GB) | needed by Isaac Sim, also in headless mode |
| Isaac Sim | **6.2** (tested `6.2.0-rc.14`) | path in `configs/isaac.yaml → root` |
| Isaac extensions | `omni.anim.behavior.core`, `omni.anim.navigation.core`, `omni.anim.retarget.core`, `omni.anim.graph.core` (110.4) | ship with Isaac 6.2 in `extscache/`; enabled by the script |
| Host Python | ≥ 3.10 | only `pyyaml` (plus `usd-core` and `pytest` for the tests) |
| Network | access to NVIDIA's content server | the human motion library is loaded from a URL; see 2.4 for offline use |
| Inputs | ≥ 1 finished humans run, ≥ 1 finished rooms run | `output/humans/run-*`, `output/rooms/run-*` |

`omni.anim.people` (the people extension of Isaac 4.x / 5.x) **no longer exists in Isaac 6.2**. This pipeline uses its
successor, the behavior system `omni.anim.behavior`. Isaac 4.x / 5.x are not supported.

## 2.2 Install

```bash
cd synthetic-data-generation/sdg
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # pyyaml, usd-core, pytest
.venv/bin/python -m pytest -q tests            # 13 tests, < 1 s
.venv/bin/python scripts/run_pipeline.py --dry-run
```

A dry run must list the humans and rooms it found and print the visit plan, without errors.

The animation runs inside **Isaac Sim's own Python** (`<isaac root>/python.sh`), which the pipeline starts itself.
Do not install Isaac packages into the `.venv`.

## 2.3 Isaac Sim path

Edit `configs/isaac.yaml`:

```yaml
root: /home/gehc-1/Joseph/NVIDIA/isaac-sim     # folder containing python.sh and VERSION
python: python.sh
```

or pass `--isaac-root /path/to/isaac-sim` on each run. The pipeline checks that the folder and `python.sh` exist and
reads `VERSION` into the log and `sd_info.json`.

## 2.4 Motion library (natural motion)

Walking, turning and idle motion come from NVIDIA's **HumanMotionLibrary** (`configs/isaac.yaml → motion_library`),
which by default is a URL on NVIDIA's content server. Isaac caches it after the first load (about 0.2 s afterwards).

To run offline, download the motion library folder (the `.usd` and the files it references) to a local or Nucleus
path, and set `motion_library` to that path.

## 2.5 First run

* The first Isaac start on a machine compiles RTX shaders, which can take **several minutes** with no console output
  and low GPU load. Later starts take about 15 s.
* A visit then takes about 80 s headless: about 30 s of stage set-up (room, motion library, retarget, NavMesh) plus
  about 50 s of animation.
* GUI mode plays the animation at wall-clock speed (`isaac.realtime: true`).

## 2.6 Isaac preferences

The pipeline changes only **session** settings and the in-memory stage's `navmeshSettings`. It does not write
Isaac's saved preferences (`user.config.json`), so your interactive Isaac sessions keep their own NavMesh and behavior
defaults.
