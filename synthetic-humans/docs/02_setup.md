# 2. Setup

> Setting up a new machine? Follow the 6 steps in the [README](../README.md#setup-on-a-new-machine-one-time-15-min);
> this page explains each part in detail.

## 2.1 Requirements

| Component | Version | Notes |
|---|---|---|
| Python (system) | ≥ 3.10 | runs the orchestrator, sampling, validation and reports |
| Blender | ≥ 4.2, tested 5.2.x | any install type; snap: `/snap/bin/blender` |
| MPFB extension | ≥ 2.0.18 | installed from Blender's extension platform |
| GPU (optional) | any CUDA/OptiX GPU | texture bake on GPU (2–4 s); CPU also works |
| Disk | ~60 MB per human | 2048² skin texture dominates |

`check_env.py` verifies all of this (see 2.8).

## 2.2 Python environment

```bash
cd synthetic-data-generation/synthetic-humans
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # pyyaml, numpy, usd-core, pillow, pytest
```

Always run the scripts with `.venv/bin/python` (or activate the venv first).

## 2.3 Blender + MPFB

1. Install Blender (≥ 4.2).
2. Blender → *Edit → Preferences → Get Extensions*, search **MPFB**, then *Install*.
3. Set `export.blender_bin` in `configs/export.yaml` to the Blender executable.

The pipeline enables MPFB itself in every headless process (`addon_utils.enable`). The module
name is auto-detected (e.g. `bl_ext.blender_org.mpfb`). Set `export.mpfb_module` only if auto
detection fails.

## 2.4 MakeHuman asset packs (hair, skins, garments)

MPFB ships the base mesh, targets, rigs and a procedural skin. **Hair, eyebrows, eyelashes, skin
textures and garments come from MakeHuman asset packs.** They are not part of this project and are
**not downloaded unless you ask for it**. Any of these installs the missing packs:

```bash
.venv/bin/python scripts/check_env.py --setup                    # recommended: packs + gowns + full check
.venv/bin/python scripts/check_env.py --install-packs            # packs + check
.venv/bin/python scripts/run_pipeline.py --install-packs ...     # packs, then the normal run
.venv/bin/python scripts/install_asset_packs.py                  # packs only
.venv/bin/python scripts/install_asset_packs.py --all            # reinstall every pack
.venv/bin/python scripts/install_asset_packs.py --from-dir DIR   # offline: zips copied to DIR
.venv/bin/python scripts/install_asset_packs.py --list           # installed packs + asset counts
```

or set `install_missing_packs: true` in `export.yaml` so every run installs what is missing.

| `export.yaml` key | Default | Meaning |
|---|---|---|
| `asset_packs` | 7 packs | `{name, file, license}` per pack; download URL = `<asset_packs_url>/<name>/<file>` |
| `asset_packs_url` | `https://files2.makehumancommunity.org/asset_packs` | download server |
| `asset_packs_download_dir` | `~/.cache/sdg_asset_packs` | downloaded zips are kept here; an existing zip is not downloaded again |
| `asset_packs_target` | auto | MPFB user data dir (auto-detected) or an explicit path |
| `install_missing_packs` | false | `true` = install missing packs automatically on every run |
| `asset_mode` | auto | `auto`: missing packs → WARN, run continues; `required`: → FAIL |

A pack counts as installed when `<MPFB user data>/packs/<name>.json` exists (every pack zip
contains that file). Downloads go to `<file>.part` first and are checked to be valid zips, so an
interrupted download is simply restarted next time.

**Without packs** the pipeline still runs: procedural skin, generated eyes, no hair / eyebrows /
eyelashes / shoes, and every human falls back to the hospital gown (`clothing.fallback_variant`).

The pack list is in `configs/export.yaml → asset_packs`:

| Pack | License | Used for |
|---|---|---|
| makehuman_system_assets | CC0 | hair (10 styles), eyebrows (12), eyelashes (4), skins, eyes, system suits / shoes |
| shirts01 | CC0 | polo shirt, tucked tee, sweaters |
| shirts02 | CC-BY | striped shirt, blouse, knitted sweaters, cardigan |
| pants01 | CC0 | wool pants |
| pants02 | CC-BY | male / female trousers |
| skirts01 | CC0 | skirts |
| shoes02 | CC-BY | oxford / monk-strap shoes, ballet flats, Mary Janes, sneakers, saddle shoes |

The zips are extracted (data files only, path-checked) into MPFB's user data directory
(`~/.config/blender/<ver>/extensions/.user/blender_org/mpfb/data`; snap installs may use
`~/snap/blender/common/.config/blender/…`), the same location MPFB's *Install pack from zip* uses.
That folder belongs to one Blender version: after a Blender upgrade, run `check_env.py --setup`
again (the cached zips are reused). CC-BY assets require attribution: the garment names (author prefix,
e.g. `mindfront_…`) are recorded per human in `H0001.json → clothing.items`.

How the packs are used:

* **Hair / eyebrows / eyelashes:** names from `appearance.yaml → hair / eyebrows / eyelashes`. Hair and
  eyebrows are tinted per human (`hair.rgb`) and exported with an alpha cut-out (UsdPreviewSurface
  `opacityThreshold`).
* **Garments:** `clothing.yaml` variants pick from the installed packs by name, per sex. Each
  garment's final colour is baked to a texture, because MakeHuman garments often store a grey
  shading map multiplied by a colour.
* **Shoes:** the body vertices inside them are removed at export (`hide_body_under: [feet]`), so feet
  never poke through.
* **Skin:** stays the MPFB procedural layered skin (`skin.source: layered`, exact Monk tones).
  `mhmat` switches to the pack's photographic skins.

Set `export.asset_mode: required` to make the preflight **fail** when packs are missing.

## 2.5 Hospital gowns (one-time, automatic)

MPFB has no hospital gown, so the pipeline **generates gown assets with MPFB's own MakeClothes
services**:

```bash
.venv/bin/python scripts/make_gown.py                     # all variants in configs/gown.yaml
.venv/bin/python scripts/make_gown.py --variant gown_short
```

`check_env.py --fix` and `run_pipeline.py` run it automatically when a gown file is missing.

The gown is modelled on the classic hospital gown: knee length, natural shoulders, round
neckline, short sleeves with a white trim band, open back with ties, striped or solid fabric.
How it works (`sdg_humans/blender/gown/`):

1. **Neutral body:** `HumanService.create_human()` (all macros 0.5, helpers visible) with the
   default rig. Each vertex is labelled with its dominant bone (`regions.py`).
2. **Upper shell** (`shell.py`): the body's own faces dominated by torso bones, plus upper-arm faces
   up to `sleeve_ends`, from the round neckline down to `seam_below_armpit_cm`. It is smoothed
   (`shell_smooth_iterations`) and offset by `looseness_cm`, with the sleeves widening by
   `sleeve_widen_cm` towards the trim. Using the real body surface is what gives natural shoulders.
3. **Lower drape** (`profile.py`, `body_parts.py`): for each height band and 64 directions the
   outermost torso/leg vertex is found (arms, shoulders, neck excluded). From just below the armpits
   the fabric *falls*: each ring is at least as wide as the ring above it, plus a slight A-line flare.
   It hangs straight from chest and belly to the knee (`lengths.knee = 1.0` = knee joint height) and
   envelops both legs like a dress.
4. **Seam:** below the armpits the shell is pushed `seam_cover_cm` outside the drape, so the join
   reads as a yoke seam (no fold or gap).
5. **Back:** an open strip below the armpits (`back_opening_width_cm`), bow ties at `tie_heights`.
6. **UVs / textures:** u runs around the body (vertical stripes, seam at the back). The last part of
   each sleeve maps to the white trim band of `stripes_mask.png`.
7. **Asset:** vertex groups `body` / `helper-skirt`, then MakeClothes
   (`ClothesService.create_mhclo_from_clothes_matching`, `Mhclo.write_mhclo`).
8. **At build time** (`gown_style.py`): per-human fabric (`clothing.gown_colors`), edge-pinned
   smoothing, a slight inflation and thickness, and **weight smoothing** over the lower 60 % of the
   gown (`gown_shaping.weight_smooth_*`). The hem blends between both legs and the pelvis, so the
   gown sways naturally instead of splitting when the character walks or jumps.

To hand-edit a gown: open `assets/custom/hospital_gown/gown_standard.obj` next to a neutral MPFB
human in Blender, edit it, keep exactly one vertex group per vertex (`body` / `helper-skirt`),
then use MPFB *Create assets → MakeClothes → Save as files* to overwrite the `.mhclo`.

## 2.6 Landmark anchors (one-time, already done)

`configs/landmarks.yaml` ships with calibrated anchor vertex IDs. To recompute them (e.g. after an
MPFB update that changes the base mesh):

```bash
.venv/bin/python scripts/calibrate_anchors.py --auto --overwrite
```

See [06_landmarks.md](06_landmarks.md) for how to refine an anchor by hand.

## 2.7 Output directory

`export.output_root` (default `/home/gehc-1/Joseph/SandBox/synthetic-data-generation/output`)
must be writable. Each run creates `run-<timestamp>` inside it. Override per run with
`--output-root`.

## 2.8 Check the environment

```bash
.venv/bin/python scripts/check_env.py            # check only
.venv/bin/python scripts/check_env.py --fix      # + generate missing gowns
.venv/bin/python scripts/check_env.py --setup    # + generate missing gowns + install missing asset packs
```

Example output:

```
[config]    OK   all YAML files valid
[preflight] OK   python            Python 3.12.3
[preflight] OK   python packages   pyyaml, numpy, usd-core, pillow
[preflight] OK   blender           Blender 5.2.2
[preflight] OK   mpfb              MPFB 2.0.18 at ~/.config/blender/5.2/extensions/blender_org/mpfb
[preflight] OK   asset packs cfg   7/7 configured packs installed
[preflight] OK   mpfb import       bl_ext.blender_org.mpfb 2.0.18 (Blender 5.2.2 LTS)
[preflight] OK   asset packs       skins 23, eyes 2, eyebrows 12, eyelashes 4, hair 10, clothes 90
[preflight] OK   gpu (bake)        OPTIX:Tesla T4
[preflight] OK   clothing assets   all fixed clothing assets present
[preflight] OK   landmark anchors  26 anchors calibrated
[preflight] OK   output dir        /…/output writable, 80.1 GB free (need ~9.0 GB)
[preflight] PASSED
```

| Check | Rule | On failure |
|---|---|---|
| python | ≥ `export.min_python` | error |
| python packages | pyyaml, numpy, usd-core, pillow importable | error (pip command shown) |
| blender | binary exists, version ≥ `min_blender`; warns if not `tested_blender` | error / warn |
| mpfb | extension on disk, version ≥ `min_mpfb` | error |
| mpfb import | headless Blender can enable MPFB | error |
| asset packs cfg | every pack in `export.asset_packs` installed (installs them with `--setup` / `--install-packs`) | warn (`asset_mode: auto`) / error (`required`) |
| asset packs | Blender sees system assets (skins, hair, …) | warn (`asset_mode: auto`) / error (`required`) |
| gpu (bake) | Cycles sees a GPU | warn → CPU bake |
| clothing assets | every fixed `asset:` file exists (auto-generated with `--fix`) | error |
| landmark anchors | no `null` anchors | error |
| output dir | writable; free disk ≥ count × `est_mb_per_human` | error / warn |
