# anny-humans

Config-driven generator of **unique, realistic, rigged, landmark-annotated synthetic patients** for the X-ray
room digital twin, built on NAVER's **[Anny](https://github.com/naver/anny)** body model (Apache-2.0, PyTorch).
Pure Python: no Blender. Output is **Isaac-Sim-ready USD** with the same layout, skeleton and metadata as
the MPFB pipeline (`../mpfb-humans`), so `../sdg` can use these humans directly.

Every human:

- is an **adult inside the configured age range** (`population.age_range`, 18 ≤ min < max ≤ 70). Anny's
  WHO-calibrated age phenotype shapes the body for that age;
- differs in sex, age, ethnicity (Anny race mix), skin tone (Monk scale), height (solved to the target),
  somatotype (→ measured weight / BMI), face (MakeHuman detail targets), eye colour, hair and clothing. A minimum
  identity distance between any two humans is enforced;
- has the **MPFB / MakeHuman 163-bone rig** (Anny `rig: makehuman`) under an identity `SkelOrigin` root, plus
  **175 `LM_` landmark joints and 36 `AN_` anatomical frames** (C1–S5 vertebral bodies, ribs, sternum, scapulae, joint
  centres, ISB frames) and **83 anatomical bone meshes**, all skinned to the rig. Same rules as MPFB;
- has a **realistic skin**: a MakeHuman photo texture matched to the Monk tone in CIELAB, generated
  **pore / age-wrinkle normal maps** and **roughness maps**, and an **MDL OmniSurface** shader with **subsurface
  scattering** for Isaac RTX. A UsdPreviewSurface is always written as the portable fallback;
- has MakeHuman **eyes** (iris colour), **hair, eyebrows and eyelashes** (alpha cut-out, hair normal maps, greying
  with age);
- wears **office clothing**: shirt or t-shirt with jeans; women also a knee-length office skirt. Colours are random
  and footwear depends on sex. Garments are fitted with MakeHuman's MHCLO rule, with layering, poke-through correction,
  and covered skin hidden (`holeIndices`) so skin can't poke through when the human moves;
- is written to its own folder: `USD + metadata JSON + preview PNG + textures`.

Not in scope: animation (no `_anim.usda`), skeleton and landmark PNGs, and hospital gowns (for now).

## Setup (one time)

| Item | Version |
|---|---|
| Python | ≥ 3.10 (tested 3.12) |
| GPU | optional (tested Tesla T4); CPU works |
| MakeHuman asset packs | installed once for the MPFB pipeline (`mpfb-humans/scripts/install_asset_packs.py`); this pipeline reads them from MPFB's user data dir |
| Disk | ~25 MB per human (150 humans ≈ 4 GB) |

```bash
cd synthetic-data-generation/anny-humans
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/check_env.py          # preflight: packages, Anny, device, asset packs, anchors, disk
```

The first Anny model load builds its cache in `~/.cache/anny` (a few minutes, once).

## Run

```bash
.venv/bin/python scripts/run_pipeline.py --count 6                       # quick test
.venv/bin/python scripts/run_pipeline.py                                 # population.count (150) humans
.venv/bin/python scripts/run_pipeline.py --age-min 30 --age-max 60      # age range override
.venv/bin/python scripts/run_pipeline.py --resume --run-dir <run dir>    # continue an interrupted run
.venv/bin/python scripts/run_pipeline.py --only A0004 --run-dir <run>    # rebuild one human
.venv/bin/python scripts/sample_population.py --dry-run                  # population table only
.venv/bin/python scripts/validate_usd.py <run dir>                       # Isaac compatibility checks
.venv/bin/python -m pytest -q tests                                      # 50 tests (~1 min, builds one human)
```

A human takes about 40 s on this machine (2 CPU cores): 18 s of that is the bone meshes, 10 s the skin maps.
Exit codes: 0 ok / warn, 1 some humans failed, 2 config or preflight error.

### Output

```
output/anny-humans/run-<timestamp>/
  manifest.json  population.csv  results.json  summary.json  contact_sheet.png  preflight.json
  resolved_config.json  config_snapshot/  logs/{pipeline.log, errors.log, humans/<id>.log}
  humans/<id>/<id>.usd  <id>.json  <id>.png  textures/<id>_{skin,skin_normal,skin_roughness,eyes,hair,...}.png
```

To animate these humans in `../sdg`, point `sdg/configs/run.yaml → humans.root` at
`output/anny-humans` or at one of its runs. The skeleton uses MPFB's joint names, so
`sdg/configs/retarget_mpfb.yaml` applies unchanged.

## Configuration

`configs/*.yaml` keep the MPFB pipeline's files and meaning. Differences:

| File | Change |
|---|---|
| `population.yaml` | **`age_range: {min, max}`** (18–70); age bands are clipped to it; `age_years_to_anny` (Anny's calibrated anchors); ids `A0001…` |
| `appearance.yaml` | `skin.source: auto / mhmat / flat`, `skin.detail` (normal / roughness maps), `skin.subsurface`, `eyes.pack_materials` |
| `clothing.yaml` | office clothing only (`shirt` 58 %, `tshirt` 42 %); `skirt_shaping` (drape and blended hem weights) |
| `body.yaml` | new: Anny `rig`, `topology`, local changes, height-solve scale limit |
| `export.yaml` | no Blender / bake / animation keys; `device`, `anny_cache_dir`, `makehuman_assets_dir`, `usd.mdl`, `usd.normals` |
| `anatomy.yaml`, `landmarks.yaml`, `poses.yaml`, `logging.yaml` | unchanged (anchor vertex IDs are hm08, identical in Anny) |

Details: [docs/02_configuration.md](docs/02_configuration.md).

## Isaac Sim checks (done by the user)

Headless checks (`validate_usd.py`, tests) cover the structure. In Isaac Sim 6.2:

1. *File → Open* `humans/A0001/A0001.usd`: the human stands on the floor facing -Y, 1 SkelRoot,
   materials render with RTX (skin subsurface, hair cut-outs).
2. Stage: `A0001_rig/A0001_rig` skeleton has 375 joints starting `SkelOrigin/root/...`; the `bone_*` meshes are
   `guide` (hidden).
3. Run `sdg` with `humans.root` set to the run directory to confirm retargeting and walking.

Documentation: [docs/](docs/): overview, setup, configuration, pipeline, USD / Isaac, metadata schema,
MPFB vs Anny.
