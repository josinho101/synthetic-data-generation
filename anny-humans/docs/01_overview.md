# 1. Overview

`anny-humans` builds synthetic X-ray patients from the **Anny** parametric body model and writes them as Isaac Sim
USD. It is a Blender-free alternative to the MPFB pipeline (`../mpfb-humans`) with the same outputs.

## 1.1 Why Anny with the MakeHuman rig and topology

Anny is built from MakeHuman / MPFB2 assets. With `rig: makehuman` and `topology: makehuman`:

| Property | Consequence |
|---|---|
| Mesh = hm08 base mesh (19 158 vertices incl. helpers, quads) | MPFB landmark anchor IDs, every MHCLO asset (clothes, hair, brows, lashes, eyes) and MakeHuman skin UVs apply unchanged |
| Rest space = MPFB's Blender space (m, Z up, front -Y) | MHCLO fitting formula and landmark rules work as they are |
| Rig = MPFB default rig (163 bones, Blender bone orientation) | same USD joint names (`upperarm01_L`, …): `sdg` retarget map, `landmarks.yaml` parents, `poses.yaml` roles |
| Phenotypes = MakeHuman macros (gender, age, muscle, weight, height, proportions, cup / firmness, race) | the MPFB population config keeps its meaning |
| Age calibrated to years (WHO data) | `age_years_to_anny` uses Anny's own anchors |

**MakeHuman rig vs Anny rig for X-ray pose data.** Anny's own rig (`rig: anny`) is the same body skeleton without
the 59 face / tongue / eye bones, re-oriented for stable optimisation. For exam positioning the MakeHuman rig is the
better choice: it keeps `jaw` (open-mouth C1/C2 view), `eye_L/R` (gaze, IOML head positioning, retarget eye tags),
the scapula bone `shoulder01`, the split twist bones (pronation / supination for wrist and elbow views) and the
metacarpals.

## 1.2 Steps (one human, ~40 s)

```
manifest spec ──► fit           Anny phenotypes + face local changes → bisection on "height" to the target
                                 stature → soles on z = 0 → mass = body volume × density → BMI
              ──► skin          MakeHuman photo skin → CIELAB tone match → generated normal + roughness maps
              ──► body parts    eyes (pack mesh, iris texture), eyebrows, eyelashes, hair (tinted) — MHCLO fit
              ──► clothing      slot picking (clothing_match) → MHCLO fit → recolour / sock recolour → skirt drape
                                 → outer-layer offset → poke-through push-out
              ──► floor         lift everything so the shoe soles stand on z = 0
              ──► landmarks     anchors (hm08 IDs) → spine C1–S5 → spinal shape → ISB frames → derived joints
              ──► measure       landmark heights, chest / abdomen width + depth, biacromial width
              ──► anatomy       83 bone meshes from landmarks + rig, kept inside the skin, rigidly skinned
              ──► skeleton      SkelOrigin + 163 rig joints + 211 LM_/AN_ joints; body = hm08 "body" group
              ──► USD           UsdSkel + UsdPreviewSurface + MDL OmniSurface
              ──► usd_post      clothing holeIndices, anatomy purpose = guide
              ──► preview       <id>.png rendered from the final USD
              ──► validate      Isaac checks (pipeline/validate.py)
```

Workers are threads sharing one Anny model (`export.workers`). Each human logs to `logs/humans/<id>.log`.

## 1.3 Code map

| Module | Role | Origin |
|---|---|---|
| `model.py`, `body_fit.py` | Anny wrapper, height / mass solve | new |
| `proxy_fit.py` | MHCLO / OBJ / MHMAT parsing, fitting, weight transfer | port of MPFB `ClothesService.fit_clothes_to_human` |
| `garments.py`, `skin.py`, `textures.py` | body parts, clothing, skin, texture ops | port of `blender/assets.py`, `garment_fit.py`, `materials.py`, `skin.py` |
| `landmarks.py`, `measure.py`, `anatomy/` | landmarks, measurements, bone meshes | port of `blender/landmarks.py`, `measure.py`, `anatomy/` |
| `geometry.py` | BVH (trimesh + KD tree), radial depth map, `Vector` stand-in | new |
| `usd_writer.py`, `preview.py` | USD authoring, Pillow preview | new (MHR writer as base) |
| `landmark_rules.py`, `anatomy_rules.py`, `landmark_math.py`, `pose_rules.py`, `pose_usd.py` | shared rules | **identical** to MPFB and MHR |
| `sampling/`, `config/`, `metadata/`, `usd_post.py`, `clothing_match.py`, `isaac_landmarks.py`, `run_context.py`, `progress.py`, `logging_setup.py`, `pipeline/validate.py` | infrastructure | copied from MPFB, small adaptations |
