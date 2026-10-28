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
| build | 1 Blender process / human | 16 build steps (05 §5.1) | `humans/<id>/…` |
| USD post | system Python (usd-core) | clothing holes, `SkelOrigin` root joint (07 §7.2a) | `<id>.json → usd_post` |
| skeletal layer | system Python (usd-core, torch) | `zanatomy`: fit the bones, swap the rig, re-skin (14) | `<id>.usd`, `<id>.json → anatomy`, `skeleton_layer` |
| validate | system Python (usd-core) | Isaac-Sim compatibility checks (07) | `results.json` (`validation`) |
| animate | system Python (usd-core) | procedural UsdSkelAnimation + root motion (`export.animation`, off by default; skipped with a warning for `zanatomy` humans) | `<id>_anim.usda` |
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
├── work/H0001/                worker args/result JSON (debugging), skeleton_body.npz (zanatomy layer input)
└── humans/
    └── H0001/
        ├── H0001.usd          the human (UsdSkel)
        ├── H0001_anim.usda    animated Isaac Sim scene referencing H0001.usd (only with export.animation.enabled)
        ├── H0001.json         metadata (08_metadata_schema.md)
        ├── H0001.png          preview: front + left side
        ├── H0001_landmarks.png preview with landmark dots (QA; only with preview.landmark_overlay)
        ├── H0001_skeleton.png  anatomical skeleton only (front + side; procedural layer with anatomy.preview)
        └── textures/          H0001_skin.png, H0001_gown.png, …
```

## 4.4 Workers, timeouts, retries

* `export.workers` Blender processes run at the same time (ThreadPoolExecutor + subprocess).
  Each needs ~1.5 GB RAM and briefly the GPU for the bake and preview. On a 2-core machine, use 1–2.
* A worker that exceeds `timeout_s_per_human` is killed and the human is marked failed.
* A failed build is retried `retries` times. A human that still fails does not stop the run.
  It is listed in `summary.json → failed` and in `errors.log`. Rebuild it with `--only`.

## 4.5 Timing (Tesla T4, 2 CPU cores, one worker)

Measured on run-20261028-103110 (default config, `zanatomy` layer):

| Step | Typical |
|---|---|
| body + face + height fit | 1–2 s |
| skin + bake 2048² (GPU) | 7–8 s |
| rig + body parts (eyes, hair, brows, lashes) | 4–5 s |
| clothing (fit, poke-through fix, colour bake) | 8–13 s |
| floor, landmarks, measure, body dump, finalize | < 1 s |
| preview (EEVEE, front + side) | 22–37 s |
| USD export | < 1 s |
| **Blender build** | **45–67 s** |
| `zanatomy` skeleton fit + USD rewrite | 14–20 s |
| Blender start, USD post, validation | 5–10 s |
| **total per human** | **≈ 70–90 s** (wall clock; up to ~2 min for heavy outfits) → 150 humans ≈ 3–4 h |

With the `procedural` layer, the bone meshes are built in Blender and the fit is skipped; `anatomy.preview` and
`preview.landmark_overlay` (both off by default) add render time. Turning off the preview
(`preview.engines: [BLENDER_WORKBENCH]`, lower `resolution`) saves the most time.

## 4.6 Other tools

```bash
.venv/bin/python scripts/validate_usd.py output/humans/run-…          # re-validate all USDs of a run
.venv/bin/python scripts/validate_usd.py output/humans/run-…/humans/H0001/H0001.usd --json   # full result
.venv/bin/python scripts/contact_sheet.py output/humans/run-… --columns 10
.venv/bin/python scripts/make_gown.py [--variant gown_short]
.venv/bin/python scripts/calibrate_anchors.py --auto [--overwrite] [--dry-run]
.venv/bin/python scripts/garment_catalog.py [--ids U14 L06] [--category shoes]   # render the garment catalogue
.venv/bin/python scripts/sample_population.py [--dry-run] [--count N] [--seed N] [--out manifest.json]
.venv/bin/python scripts/install_asset_packs.py [--list] [--all] [--from-dir DIR]          # 02 §2.4
.venv/bin/python scripts/pose_exams.py <run>/humans/H0001/H0001.usd [--poses chest_pa spine_ap] [--out FILE]   # MPFB rig only (06 §6.8)
.venv/bin/python scripts/build_zanatomy_reference.py [--rebuild-spike]                     # 14 §Setup
```
