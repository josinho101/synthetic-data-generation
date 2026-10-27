# 4. Running the pipeline

All commands run from `synthetic-data-generation/mpfb-humans` with the venv's Python.

## 4.1 Main command

```bash
.venv/bin/python scripts/run_pipeline.py [options]
```

| Option | Meaning |
|---|---|
| `--config DIR` | configuration directory (default `configs`) |
| `--count N` | override `population.count` |
| `--seed N` | override `population.seed` |
| `--workers N` | override `export.workers` |
| `--output-root DIR` | override `export.output_root` |
| `--run-dir DIR` | reuse an existing run (requires `--resume` or `--only`) |
| `--resume` | build only humans that are not finished (no `ok`/`warn` result or no metadata) |
| `--only ID` | rebuild one human (repeatable), e.g. `--only H0042 --only H0107` |
| `--install-packs` | download + install missing MakeHuman asset packs before the checks (new machine) |
| `--skip-preflight` | skip the environment checks (not recommended) |

Exit codes: `0` all humans ok/warn · `1` at least one human failed · `2` config or preflight error.

### Typical sessions

```bash
# 1. check everything (new machine: --setup also installs asset packs and generates gowns)
.venv/bin/python scripts/check_env.py --setup

# 2. inspect the population before spending GPU time
.venv/bin/python scripts/sample_population.py --dry-run

# 3. one test human
.venv/bin/python scripts/run_pipeline.py --count 1

# 4. the full population
.venv/bin/python scripts/run_pipeline.py

# 5. interrupted (Ctrl+C, reboot)? continue where it stopped
.venv/bin/python scripts/run_pipeline.py --resume --run-dir output/humans/run-20261018-153012

# 6. rebuild one human after changing e.g. clothing.yaml (same manifest, same identity)
.venv/bin/python scripts/run_pipeline.py --only H0042 --run-dir output/humans/run-20261018-153012
```

`--resume` and `--only` reuse the run's `manifest.json`, so identities do not change. They do use
the *current* config files for build settings (clothing, export, landmarks), which lets you fix
build issues without resampling. To change the population itself, start a new run.

## 4.2 Stages

| Stage | Where | What happens | Output |
|---|---|---|---|
| preflight | system Python + 1 Blender probe | environment checks (02_setup §2.8), gown auto-generation | `preflight.json` |
| sample | system Python | exact quotas → per-human specs → uniqueness | `manifest.json` |
| build | 1 Blender process / human | 13 build steps (05) | `humans/<id>/…` |
| validate | system Python (usd-core) | Isaac-Sim compatibility checks (07) | `results.json` (`validation`) |
| animate | system Python (usd-core) | procedural UsdSkelAnimation + root motion (`export.animation`, off by default) | `<id>_anim.usda` |
| report | system Python | CSV, summary, contact sheet | `population.csv`, `summary.json`, `contact_sheet.png` |

## 4.3 Run directory

```
<output_root>/run-20261018-153012/
├── config_snapshot/*.yaml     exact YAML used
├── resolved_config.json       merged config (read by Blender workers)
├── preflight.json             check results
├── manifest.json              resolved spec of every human (inputs)
├── results.json               per-human build result: status, timings, warnings, validation
├── population.csv             one row per human (inputs + measurements)
├── summary.json               configured vs achieved distributions, body stats, failures, timings
├── contact_sheet.png          grid of all previews
├── logs/
│   ├── pipeline.log           orchestrator, INFO (default)
│   ├── errors.log             all ERROR records
│   └── humans/
│       ├── H0001.log          worker log (INFO): every step with timing, measurements, asset picks
│       └── H0001.blender.log  raw Blender / MPFB console output
├── work/H0001/                worker args/result JSON (debugging)
└── humans/
    └── H0001/
        ├── H0001.usd          the human (UsdSkel)
        ├── H0001_anim.usda    animated Isaac Sim scene referencing H0001.usd (only with export.animation.enabled)
        ├── H0001.json         metadata (08_metadata_schema.md)
        ├── H0001.png          preview: front + left side
        ├── H0001_landmarks.png preview with landmark dots (QA; only with preview.landmark_overlay)
        ├── H0001_skeleton.png  anatomical skeleton only (front + side; only with anatomy.preview)
        └── textures/          H0001_skin.png, H0001_gown.png, …
```

## 4.4 Workers, timeouts, retries

* `export.workers` Blender processes run at the same time (ThreadPoolExecutor + subprocess).
  Each needs ~1.5 GB RAM and briefly the GPU for the bake and preview. On a 2-core machine, use 1–2.
* A worker that exceeds `timeout_s_per_human` is killed and the human is marked failed.
* A failed build is retried `retries` times. A human that still fails does not stop the run.
  It is listed in `summary.json → failed` and in `errors.log`. Rebuild it with `--only`.

## 4.5 Timing (Tesla T4, 2 CPU cores, one worker)

| Step | Typical |
|---|---|
| Blender + MPFB start | 3–5 s |
| body + face + height fit | 1–2 s |
| skin bake 2048² (GPU) | 3–4 s |
| rig, eyes, clothing, landmarks | 1–2 s |
| anatomical skeleton | < 1 s |
| previews (EEVEE: body + skeleton, 2 views each) | 70–85 s |
| USD export + validation | < 2 s |
| **total per human** | **≈ 85–95 s** → 150 humans ≈ 3.5–4 h (`anatomy.preview` and `preview.landmark_overlay` are off by default; turning them on adds render time) |

Turning off the preview (`preview.engines: [BLENDER_WORKBENCH]`, lower `resolution`) saves the most time.

## 4.6 Other tools

```bash
.venv/bin/python scripts/validate_usd.py output/humans/run-…          # re-validate all USDs of a run
.venv/bin/python scripts/validate_usd.py output/humans/run-…/humans/H0001/H0001.usd
.venv/bin/python scripts/contact_sheet.py output/humans/run-… --columns 10
.venv/bin/python scripts/make_gown.py [--variant gown_short]
.venv/bin/python scripts/calibrate_anchors.py --auto [--overwrite] [--dry-run]
.venv/bin/python scripts/garment_catalog.py [--ids U14 L06] [--category shoes]   # render the garment catalogue
.venv/bin/python scripts/sample_population.py [--dry-run] [--out manifest.json]
```
