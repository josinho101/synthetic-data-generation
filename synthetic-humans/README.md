# synthetic-humans

Config-driven generator of **distinct, rigged, landmark-annotated synthetic patients** for the
X-ray room digital twin. Humans are built with the **MPFB** extension in **Blender**, then
exported as **Isaac-Sim-compatible USD** (UsdSkel skeleton, meters, Z-up, UsdPreviewSurface
materials with baked textures).

Every human:

- differs in sex, age, ethnicity (MPFB race mix), skin tone (Monk scale), height, somatotype
  (→ weight / BMI), face shape (MPFB detail targets), eye colour and clothing;
- carries **128 landmark joints + 5 anatomical frames** in its skeleton (C1–C7, T1–T12, L1–L5, S1–S5 as oriented vertebral-body
  *and* skin-surface points; head, sternum, scapulae, pelvis, elbow, wrist, knee and ankle
  landmarks; ISB-style skull, thorax, pelvis and scapula frames, see
  [docs/06_landmarks.md](docs/06_landmarks.md)). The landmarks follow any animation applied in Isaac Sim;
- has a **schematic anatomical skeleton** (~80 bone meshes: skull, vertebrae, ribs, sternum,
  shoulder girdle, pelvis, limbs, hands, feet) inside the body, skinned to the rig;
- has **hair, eyebrows and eyelashes** (MakeHuman system assets, tinted per human);
- wears a **hospital gown** (striped or solid, natural shoulders, short trimmed sleeves, knee length,
  open back with ties) or a **shirt / t-shirt with jeans** (women also a knee-length office skirt),
  in random colours, with **footwear by sex**;
- can be posed into the **X-ray exam poses** with coupled spine / scapula / rib motion and a range-of-motion
  check: `scripts/pose_exams.py` (see [docs/06_landmarks.md](docs/06_landmarks.md#68-derived-joints-spinal-shape-and-exam-posing-2026-10-26));
- can come with an **animated Isaac Sim scene** `<id>_anim.usda` (idle → walk → idle → jump → walk
  back → idle; `export.animation.enabled`, off by default), see [isaac/README.md](isaac/README.md);
- is written to its own folder: `USD + metadata JSON + preview PNGs + textures`.

## Setup on a new machine (one time, ~15 min)

### What you need

| Item | Version | How to get it |
|---|---|---|
| OS | Linux (tested Ubuntu, kernel 6.x); macOS / Windows paths are also detected | |
| Python | ≥ 3.10 (tested 3.12) | system package, e.g. `sudo apt install python3 python3-venv` |
| Blender | ≥ 4.2 (tested 5.2.2) | [blender.org](https://www.blender.org/download/) or `sudo snap install blender --classic` |
| MPFB extension | ≥ 2.0.18 | inside Blender (step 2) |
| Internet | once, ~800 MB | MakeHuman asset packs (step 4); an offline route is below |
| GPU | optional (CUDA / OptiX) | texture bake is faster; CPU works too |
| Disk | ~1 GB for assets + ~60 MB per human | 150 humans ≈ 9 GB |

### Steps

**1. Get the project** (copy or clone `synthetic-data-generation/` to the new machine):

```bash
cd synthetic-data-generation/synthetic-humans
```

**2. Install MPFB in Blender:** start Blender → *Edit → Preferences → Get Extensions* → search
**MPFB** → *Install*. Close Blender. (The pipeline enables MPFB itself in its headless Blender
processes; you never need to open Blender again.)

**3. Python environment:**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # pyyaml, numpy, usd-core, pillow, pytest
```

**4. Edit `configs/export.yaml`** for this machine:

```yaml
output_root: /path/where/runs/go        # must be writable; every run creates run-<timestamp>/ inside
blender_bin: /snap/bin/blender          # `which blender`, or e.g. /opt/blender-5.2/blender
workers: 1                              # parallel Blender processes (~1.5 GB RAM each)
```

**5. Install the asset packs + check everything** (one command):

```bash
.venv/bin/python scripts/check_env.py --setup
```

`--setup` does all one-time preparation and then runs the environment check:

* downloads the **MakeHuman asset packs** listed in `export.yaml → asset_packs` (hair, eyebrows,
  eyelashes, skins, shirts, trousers, skirts, suits, shoes; ~800 MB, about 5–10 min) from
  `files2.makehumancommunity.org` and installs them into MPFB's user data folder
  (`~/.config/blender/<version>/extensions/.user/blender_org/mpfb/data/`). Packs that are already
  installed are skipped, and the zips stay in `~/.cache/sdg_asset_packs/` for a reinstall;
* generates the **hospital gown** assets if `assets/custom/hospital_gown/` is missing;
* checks Python, packages, Blender, MPFB, assets, GPU, landmark anchors and the output folder.

It must end with `[preflight] PASSED` and the line
`OK   asset packs cfg   7/7 configured packs installed`. Any `FAIL` line says what to fix
(see [docs/10_troubleshooting.md](docs/10_troubleshooting.md)).

**6. Generate a test human, then the population:**

```bash
.venv/bin/python scripts/run_pipeline.py --count 1    # ~2 min; open humans/H0001/H0001.png to check
.venv/bin/python scripts/run_pipeline.py              # full population (configs/population.yaml)
```

### Asset packs: the details

* **Are they downloaded automatically?** Only when you ask: `check_env.py --setup`,
  `check_env.py --install-packs`, `run_pipeline.py --install-packs`, or
  `install_missing_packs: true` in `configs/export.yaml` (then every run installs whatever is
  missing). Without that, a run on a machine without packs **still works** but prints
  `WARN asset packs …`: every human then wears a hospital gown, with no hair, eyebrows,
  eyelashes or shoes. Set `asset_mode: required` to make that an error instead.
* **One step:** `run_pipeline.py --install-packs --count 1` installs the packs and builds a human.
* **No internet on the target machine:** download the zips elsewhere (URLs:
  `<asset_packs_url>/<name>/<file>` from `export.yaml`, e.g.
  `https://files2.makehumancommunity.org/asset_packs/shirts01/shirts01_cc0.zip`), copy them over, then

  ```bash
  .venv/bin/python scripts/install_asset_packs.py --from-dir /path/to/zips
  ```
* **See what is installed:** `.venv/bin/python scripts/install_asset_packs.py --list`.
* **New Blender version:** each Blender version has its own extension folder. After upgrading
  (e.g. 5.2 → 5.3), install MPFB again and rerun `check_env.py --setup` (zips are reused from the
  cache, no new download).
* **Licences:** `makehuman_system_assets`, `shirts01`, `pants01`, `skirts01` are CC0;
  `shirts02`, `pants02`, `shoes02` are **CC-BY** (credit the asset authors when you publish data;
  each human's garments are listed in `H0001.json → clothing.items`).
* **Add a pack:** add `{name, file, license}` to `export.yaml → asset_packs` (names as on
  the MakeHuman asset pack page) and rerun `check_env.py --setup`.

More detail: [docs/02_setup.md](docs/02_setup.md).

## Quick start (already set up)

```bash
cd synthetic-data-generation/synthetic-humans
.venv/bin/python scripts/check_env.py                 # environment check only
.venv/bin/python scripts/run_pipeline.py --count 1    # one human
.venv/bin/python scripts/run_pipeline.py              # full population (configs/population.yaml)
.venv/bin/python scripts/run_pipeline.py --resume --run-dir <output_root>/run-<timestamp>   # continue a run
```

Each run creates `<output_root>/run-<timestamp>/`:

```
run-20261018-153012/
├── humans/H0001/{H0001.usd, H0001.json, H0001.png, textures/}   (+ _anim.usda / _landmarks.png / _skeleton.png when enabled)
├── manifest.json  population.csv  summary.json  contact_sheet.png  results.json
├── config_snapshot/  resolved_config.json  preflight.json
└── logs/{pipeline.log, errors.log, humans/H0001.log}
```

## Configure

| File | Controls |
|---|---|
| `configs/population.yaml` | count, seed, sex %, age bands %, ethnicity %, somatotype %, height distributions, uniqueness |
| `configs/appearance.yaml` | ethnicity → race mix + skin tones, skin source, face detail ranges, eyes, hair |
| `configs/clothing.yaml` | clothing variants % (hospital gowns, MPFB clothes slots), gown colours and shaping |
| `configs/gown.yaml` | hospital gown generator (length, sleeves, looseness, neckline, back opening) |
| `configs/landmarks.yaml` | anchor vertices, vertebra distribution, parent bones, reported heights |
| `configs/anatomy.yaml` | anatomical skeleton (bone meshes): parts, colour, rib shape, soft tissue |
| `configs/export.yaml` | output root, Blender path, workers, USD / preview / bake options |
| `configs/logging.yaml` | log levels, files, rotation |

## Documentation

1. [Overview & architecture](docs/01_overview.md)
2. [Setup](docs/02_setup.md)
3. [Configuration reference](docs/03_configuration.md)
4. [Running the pipeline](docs/04_pipeline.md)
5. [How a human is created (body & identity)](docs/05_body_and_identity.md)
6. [Landmarks](docs/06_landmarks.md)
7. [USD & Isaac Sim](docs/07_usd_isaac_sim.md)
8. [Metadata schema](docs/08_metadata_schema.md)
9. [Logging & monitoring](docs/09_logging_and_monitoring.md)
10. [Troubleshooting](docs/10_troubleshooting.md)
11. [Anatomical skeleton](docs/11_anatomy.md)
12. [Animation in Isaac Sim](isaac/README.md)
13. [MPFB vs MHR comparison (skeleton, landmarks, exam poses)](docs/13_mpfb_vs_mhr.md)

## Tests

```bash
.venv/bin/python -m pytest -q tests      # pure-Python tests, no Blender needed
```
