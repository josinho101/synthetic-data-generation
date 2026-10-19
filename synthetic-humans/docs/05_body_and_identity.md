# 5. How a human is created

This chapter follows one human from configuration to USD.

## 5.1 Workflow

```
 population.yaml ─┐
 appearance.yaml ─┼─► STAGE 1: SAMPLE (pure Python, sdg_humans/sampling)
 clothing.yaml ───┘    ① exact quotas: sex → ethnicity → age band → somatotype → clothing
                       ② per-human seed = sha256(seed:index:attempt)
                       ③ free attributes: age, height, macros, race mix, skin tone,
                          face targets, eyes, hair, gown colour
                       ④ uniqueness check (redraw ③ if too similar to an earlier human)
                       ⑤ manifest.json entry
                              │
                              ▼
                  STAGE 2: BUILD (Blender + MPFB, sdg_humans/blender/pipeline.py)
   step         module             what it does                                         output
   ─────────────────────────────────────────────────────────────────────────────────────────────
   body         body.py            HumanService.create_human(macros, scale 0.1 = meters)   basemesh
   face         body.py            TargetService.bulk_load_targets(face targets)           shape keys
   fit          fit.py             bisection on the height macro → target stature;          height, kg, BMI
                                   feet to z = 0; volume × density → mass → BMI
   skin         skin.py            MPFB layered skin (or system skin) tinted to MST tone    material
   bake         bake.py/skin.py    Cycles DIFFUSE-colour bake → <id>_skin.png;              PNG texture
                                   material replaced by Principled + image
   rig          rig.py             add_builtin_rig("default") – 163 bones + weights         armature
   body_parts   assets.py/eyes.py  eye meshes (generated or pack), brows/lashes/hair (packs) meshes
   clothing     assets.py,         add_mhclo_asset(gown / MPFB clothes) → fitted & rigged;  meshes
                gown_style.py      gown tint, smoothing, inflation, thickness
   landmarks    landmarks.py       anchors + spine profile → 84 LM_* bones (non-deforming)  joints
   measure      measure.py         landmark heights, widths, depths                         dict
   anatomy      anatomy/*.py       ~80 bone meshes from joints + landmarks, skinned (doc 11) meshes
   preview      preview.py         EEVEE front + side PNG (+ landmark overlay, skeleton)    PNGs
   usd_export   usd_export.py      bake shape keys, drop helpers, clean weights, export     USD
   metadata     metadata/writer.py spec + measurements + landmarks + versions               JSON
                              │
                              ▼
                  STAGE 3: VALIDATE (usd-core)  →  STAGE 4: REPORT
```

## 5.2 Exact quotas (largest remainder + interleaving)

`sampling/quotas.py`:

1. **Largest remainder.** For 150 humans and ethnicity `{20, 20, 20, 25, 15}` the ideal counts
   are `30, 30, 30, 37.5, 22.5`. Floors give `30, 30, 30, 37, 22` (149). The leftover human goes
   to the largest remainder (ties by declaration order), giving `30, 30, 30, 38, 22`.
2. **Proportional sequence.** The labels are dealt in an evenly spread order (each position takes
   the label that is furthest behind its share), e.g. `{a: 2, b: 4}` → `b a b b a b`.
3. **Interleaving.** For each factor in `stratify_order`, people are sorted by their earlier labels
   (sex first, then ethnicity …) and receive the next factor's sequence. Every contiguous group,
   such as "all females", therefore gets a near-proportional mix.

Result for 150 with the shipped config: male 75 / female 75, and every sex × ethnicity cell is
balanced (e.g. 15 female African, 15 male African). Each single marginal is exact.

## 5.3 Free attributes

| Attribute | Rule (module) |
|---|---|
| age | uniform integer inside the band; MPFB age macro via `age_years_to_mpfb` (`anthropometrics.py`) |
| target height | truncated normal (sex mean/sd + ethnicity offset, clamped to [min, max]) |
| gender macro | uniform in `gender_macro.<sex>` |
| cupsize / firmness | uniform in `female_macros` (female) else 0.5 |
| weight / muscle / proportions | uniform in the somatotype ranges (`somatotype.py`) |
| race mix | profile mix ± jitter, clipped ≥ 0, normalised (`ethnicity.py`) |
| skin tone | weighted Monk level → reference RGB × (1 ± tone_jitter) |
| face | MPFB-style detail sampling (`face.py`, below) |
| eyes / hair / brows / lashes / gown colour | weighted choices (`looks.py`); grey hair probability rises after `grey_from_age` |

## 5.4 Face detail targets

`sampling/face.py` mirrors MPFB's `RandomizationService.pick_random_details`. For each section in
`appearance.face.sections` (sorted by name):

1. draw a pick count `k ∈ [min_picks, max_picks]`;
2. choose `k` distinct categories from the section's category list in MPFB's
   `data/targets/target.json` (e.g. `nose-flaring-decr-incr`);
3. per category draw a sign (decr / incr target) and a magnitude `U(0.25·dev, dev)`;
4. sided categories (`l-…`/`r-…`) get the same value on both sides when `symmetric: true`.

The result is a list like `[{"target": "nose-flaring-incr", "value": 0.31}, …]` (~25 targets per
human), loaded in Blender with `TargetService.bulk_load_targets`.

## 5.5 Uniqueness

`sampling/identity.py` defines the identity distance between two humans:

```
body_rms = RMS( gender, age, muscle, weight, proportions, race[3],
                (height − 140)/70, skin_tone/10 )         differences
face_rms = RMS over the union of both humans' face targets (missing = 0)
distance = sqrt((body_rms² + face_rms²) / 2)
```

A new human must be at least `uniqueness.min_feature_distance` away from every earlier human.
Otherwise its free attributes are redrawn with `attempt+1` (strata never change), up to
`max_resample` times. The chosen distance is stored as `identity.uniqueness_distance`. With the
shipped config the nearest-neighbour distance of 150 humans is ≥ 0.16 (threshold 0.08), so no
resampling is needed.

## 5.6 Height solver (`blender/fit.py`)

MPFB's *height* macro is relative (it interacts with gender, age and proportions), so it is solved
per human:

```
lo, hi = 0, 1
it 0: macro = 0.5   → measure stature (evaluated mesh, helpers masked, max z − min z)
it n: macro = (lo+hi)/2; too short → lo = macro, too tall → hi = macro
stop when |stature − target| ≤ tolerance_cm (0.5 cm) or after max_iterations (12)
```

Each step calls `TargetService.reapply_macro_details` (≈ 0.05 s). If the target is outside what
MPFB can produce, the closest value is kept and `fit_ok=false`. Finally the mesh is moved so the
lowest vertex sits at z = 0.

## 5.7 Weight and BMI

* Volume: `bmesh.calc_volume` of the body surface (helper geometry excluded). It agrees within
  0.1 L with an independent ray-parity column integration (`geometry.body_volume_columns_m3`).
* Mass = volume × `body_density_kg_m3` (1010 kg/m³, mean whole-body density).
* BMI = mass / stature². Outside `bmi_guard` → warning and `fit_ok=false`.

### Somatotype → macros → BMI

The macro scan behind the shipped ranges (height ≈ 159 cm female / 172 cm male, age 0.6):

| weight \ muscle | 0.0 | 0.5 | 1.0 |
|---|---|---|---|
| 0.0 | F 12.5 · M 14.2 | F 16.3 · M 19.4 | F 16.5 · M 18.3 |
| 0.5 | F 21.0 · M 23.6 | F 19.1 · M 21.3 | F 18.6 · M 20.2 |
| 0.75 | F 26.5 · M 30.7 | F 20.3 · M 22.2 | F 21.0 · M 24.8 |
| 1.0 | F 32.7 · M 39.1 | F 21.5 · M 23.2 | F 23.8 · M 30.2 |

Expected BMI per somatotype (shipped ranges):

| Somatotype | weight | muscle | Typical BMI |
|---|---|---|---|
| endomorph | 0.80–1.00 | 0.00–0.25 | 27–39 |
| endomorph_mesomorph | 0.75–1.00 | 0.55–0.90 | 21–30 |
| mesomorph | 0.50–0.75 | 0.75–1.00 | 19–25 |
| mesomorph_ectomorph | 0.25–0.50 | 0.60–0.85 | 17–21 |
| ectomorph | 0.00–0.30 | 0.30–0.50 | 15–19 |
| endomorph_ectomorph | 0.55–0.75 | 0.00–0.25 | 21–27 |

## 5.8 Skin

* `layered` (default without packs): `HumanService.set_character_skin(None, basemesh,
  skin_type="LAYERED")` creates MPFB's procedural layered skin (body / face / ears / lips / nails
  regions with pores, veins and colour variation). The tone colour (sRGB → linear) is written into
  `colorgroup.SkinColor` with `SkinOverride = 1` and into the body, face and ears groups. Lips are
  derived from the tone.
* `mhmat`: the system skin best matching `"<age_variant> <base_skin> <sex>"` is loaded as
  `MAKESKIN` and its diffuse texture is multiplied by the tone.
* **Bake:** Cycles bakes the *diffuse colour* pass to a 2048² PNG (GPU when available). The
  material is then replaced by a plain Principled BSDF with that image. Blender's USD exporter can
  only translate Principled + image textures into `UsdPreviewSurface`, so this step is what makes
  the skin appear in Isaac Sim.

## 5.9 Eyes, hair and clothing

* **Eyes without packs** (`eyes.py`): the basemesh eye helper spheres are copied into two meshes.
  Faces are assigned to sclera / iris / pupil materials by the angle to the forward axis (−Y), and
  each mesh is bound 100 % to bone `eye.L` / `eye.R`.
* **Packs:** eyes, eyebrows, eyelashes and hair are loaded with `HumanService.add_mhclo_asset` and
  their materials normalised to Principled + diffuse image.
* **Clothing** (`assets.py`): every slot of the human's variant is resolved (fixed asset or
  `mpfb_slot` keyword pick, reproducible per human) and loaded with `add_mhclo_asset`, which fits
  it to the body and transfers rig weights. If nothing could be loaded, `fallback_variant` is used.
* **Gown styling** (`gown_style.py`): patterned fabric texture (stripes / solid), Smooth modifier weighted to zero at
  the cut edges, Displace (inflate) and Solidify (thickness). These are applied in the rest pose
  before export.
