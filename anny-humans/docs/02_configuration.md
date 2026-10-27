# 2. Configuration

All settings are in `configs/*.yaml` and are validated at start-up (`anny_humans/config/schema.py`).
Command-line overrides: `--count`, `--seed`, `--age-min`, `--age-max`, `--workers`, `--output-root`.

## 2.1 Age range (`population.yaml`)

```yaml
age_range: {min: 18, max: 70}      # whole years; allowed 18 <= min < max <= 70
age_bands: {"18-30": 30, "31-50": 40, "51-70": 30}
```

- Bands are **clipped** to the range. A band entirely outside it is dropped and the others are renormalised to 100 %.
  For example, `--age-min 35 --age-max 55` gives `35-50: 57 %`, `51-55: 43 %`. It is an error only when no band
  overlaps the range. The clipped bands are what the stratification, `population.csv` and `summary.json` use; the
  configured bands are kept in `resolved_config.json` as `age_bands_configured`.
- Age in years → Anny's `age` phenotype through `age_years_to_anny`. These are Anny's own WHO-calibrated anchors
  (`anny/data/shape_calibration`): 18 y = 0.77, 64 y = 0.83, 110 y = 1.0. Adult bodies span a narrow phenotype
  range, so the uniqueness distance uses the age in years instead (`sampling/identity.py`).

## 2.2 Body (`population.yaml`, `body.yaml`)

- Sex, gender range, female cup / firmness, ethnicity, somatotype and height distribution are the MPFB settings.
  Somatotype ranges set Anny's `weight`, `muscle` and `proportions` phenotypes (same semantics as the MPFB macros).
- The `height` phenotype is solved by bisection (`height_cm.tolerance_cm`, `max_iterations`). If the target is out
  of reach, a uniform scale up to `body.max_uniform_scale` (6 %) finishes it, recorded as `body.height_scale`.
- Weight and BMI are measured: the volume enclosed by the body surface × `body_density_kg_m3`.
- Anny's breast targets ignore gender. Male cup / firmness stay at 0.5, which is Anny's neutral (no breast target),
  the same as MPFB.

## 2.3 Appearance (`appearance.yaml`)

| Key | Meaning |
|---|---|
| `ethnicity_profiles` | race mix (+ jitter), base skin texture, Monk tone weights |
| `skin_albedo_lab` | measured skin albedo per Monk level; the texture median is matched to it |
| `skin.source` | `auto` (photo skin if installed, else flat), `mhmat`, `flat` |
| `skin.texture_resolution` | albedo / normal / roughness map size (2048) |
| `skin.detail` | normal strength, pore size, wrinkle gain per decade over 30, roughness range |
| `skin.subsurface` | OmniSurface subsurface weight and mean free path (mm), light → dark skin |
| `face.sections` | MakeHuman detail targets per section → Anny local changes (`incr` = +, `decr` = −) |
| `eyes.source`, `eyes.pack_materials` | MakeHuman high-poly eye mesh; colour → eye material |
| `hair`, `eyebrows`, `eyelashes` | style pools, colours, greying from `grey_from_age` |

## 2.4 Clothing (`clothing.yaml`)

Office clothing only. `shirt` (58 %) is a button-down / polo / blouse with jeans, or the office skirt for women.
`tshirt` (42 %) is a plain t-shirt with jeans, or the skirt for women. Shoes depend on sex. Slots, keyword matching,
recolour palettes and the sock recolour work as in MPFB. The office skirt is the MPFB pipeline's custom MHCLO
(`mpfb-humans/assets/custom/hospital_gown/office_skirt.mhclo`), textured as solid fabric × cotton weave.

Motion-related settings (they matter once animation is added):

| Key | Effect |
|---|---|
| `skirt_shaping.weight_smooth_*` | the lower 60 % of the skirt gets blended leg / pelvis weights, so the hem follows both legs instead of tearing |
| `skirt_shaping.smooth_*`, `inflate_cm` | relaxed drape instead of body detail |
| `layer_offset_cm`, `poke_through_clearance_cm` | outer garment offset; garment vertices kept outside the skin |
| `hide_body_under: [feet]` | body vertices really inside the shoes are removed |
| `export.usd_post.clothing_holes` | body faces covered by clothes (shoes excluded) are not rendered |

## 2.5 Export (`export.yaml`)

`output_root`, `device` (auto / cuda / cpu), `makehuman_assets_dir` (auto = MPFB user data dir), `asset_mode`
(auto / required), `workers`, `retries`, and the USD settings: format, `max_bone_influences` 4, `normals`, `mdl`.
`usd_post` and `preview` are as in MPFB.
