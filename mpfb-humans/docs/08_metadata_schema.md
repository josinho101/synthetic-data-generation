# 8. Metadata schema

## 8.1 Per-human `humans/<id>/<id>.json` (schema_version 1)

| Field | Type | Description |
|---|---|---|
| `schema_version` | int | 1 |
| `id`, `run_id`, `created`, `seed` | str/int | identity of the file; `seed` = per-human seed |
| `identity.sex` | male / female | |
| `identity.age_years`, `identity.age_band` | int, str | |
| `identity.ethnicity` | str | profile name |
| `identity.race_mix` | {asian, caucasian, african} | MPFB race macros (sum 1) |
| `identity.somatotype` | str | |
| `identity.skin_tone_mst`, `identity.skin_rgb_hex` | int 1–10, str | Monk skin tone and its reference (swatch) colour |
| `identity.skin_albedo_hex` | str | skin albedo the texture was matched to (`skin_albedo_lab`, with jitter) |
| `appearance.skin.source`, `.texture`, `.tone` | str, str, object | photo skin used (`mhmat:<file>` or `layered`), baked texture, and `tone.lab_before` / `lab_after` (median CIELAB of the skin texture) |
| `identity.eye_color`, `identity.hair` | str, {style, color} | sampled (hair only rendered with asset packs) |
| `identity.uniqueness_distance` | float | distance to the most similar earlier human |
| `mpfb_macros` | dict | final MPFB macros incl. the solved `height` macro |
| `face_targets` | [{target, value}] | MPFB detail targets applied |
| `body.target_height_cm`, `body.height_cm` | float | sampled target vs achieved stature |
| `body.weight_kg`, `body.bmi`, `body.volume_l` | float | measured (volume × density) |
| `body.fit_ok` | bool | height within tolerance and BMI within `bmi_guard` |
| `body.footwear_lift_cm` | float | how far the dressed human was raised so the shoe soles touch the floor; landmark heights (`measurements_cm`, `landmarks`) are measured **with footwear**, stature without |
| `measurements_cm.stature_cm` | float | |
| `measurements_cm.<key>` | float | heights above the floor from `landmarks.heights_from_landmarks`: `vertex_height_cm`, `ear_height_left_cm`, `ear_height_right_cm`, `nasion_height_cm`, `eye_height_cm`, `chin_height_cm`, `c7_height_cm`, `shoulder_height_left_cm`, `shoulder_height_right_cm`, `jugular_notch_height_cm`, `sternal_angle_height_cm`, `xiphoid_height_cm`, `scapula_inferior_angle_height_cm`, `navel_height_cm`, `iliac_crest_height_cm`, `asis_height_cm`, `trochanter_height_cm` |
| `measurements_cm.chest_width_cm`, `chest_ap_depth_cm` | float | at xiphoid height; arm vertices excluded by their dominant rig bone |
| `measurements_cm.abdomen_width_cm`, `abdomen_ap_depth_cm` | float | at navel height |
| `measurements_cm.biacromial_width_cm` | float | acromion to acromion |
| `appearance.body_parts` | {eyes, eyebrows, eyelashes, hair} | asset used, `generated`, or null |
| `clothing.variant`, `clothing.gown_color` | str | variant `none` when `clothing.enabled` is false |
| `clothing.items` | [{slot, asset, object, variant, color, delete_group, hides_body, …}] | garments actually worn (`color` = recolour name or null; `hides_body` = body removed under it, e.g. shoes) |
| `skeleton.rig`, `bone_count`, `deform_bone_count`, `landmark_joint_count` | | USD skeleton. `zanatomy`: `zanatomy_anatomical`, 157, 156, 0. `procedural` / `none`: `mpfb_default`, 374, 163, 175 (+ `frame_joint_count` 36; `SkelOrigin` is added later by `usd_post`) |
| `skeleton.usd_root_prim`, `skeleton.usd_skeleton_prim` | str | `/H0001`, `/H0001/H0001_rig/H0001_rig` |
| `landmarks.<name>.kind` | anchor / surface / internal / centre / frame | 211 entries (06 §6.1) |
| `landmarks.<name>.level` | str | vertebra level (spine points) |
| `landmarks.<name>.vertex` | int | basemesh vertex (anchors) |
| `landmarks.<name>.rest_position_m` | [x, y, z] | rest pose, stage meters (feet at z = 0, facing −Y) |
| `landmarks.<name>.ap_depth_m`, `internal_offset_m` | float | internal points: local AP depth and offset used |
| `landmarks.<name>.axes_xyz` | 3×[x, y, z] | oriented points / frames: rest X, Y, Z axes (06 §6.1) |
| `landmarks.<name>.bone`, `parent`, `usd_joint` | str | Blender bone, parent bone, full UsdSkel joint path; `usd_joint` is `null` when the landmark is not a USD joint (`zanatomy` layer) |
| `spine_shape.target` / `before` / `after` | {kyphosis_T4_T12_deg, lordosis_L1_S1_deg, scoliosis_cobb_deg, …} | sampled vs measured spinal shape of the vertebral landmarks (06 §6.8) |
| `anatomy.count`, `anatomy.bone_meshes[]` | | bone meshes: `name`, `object`, `rig_bone`, `part`, `vertices`, `usd_prim` (doc 11 / 14) |
| `anatomy.source`, `reference_version`, `license`, `fit`, `points_m` | | `zanatomy` layer only: reference package, CC-BY-SA-4.0, fit metrics (`landmark_residual_mm`, `bone_exposed_frac_approx`, …), 272 fitted joint centres / bony landmarks in world metres (doc 14) |
| `usd_post` | {clothing_holes, anatomy_purpose, root_joint} | post-export fixes applied (07 §7.2a) |
| `skeleton_layer` | {layer, version, rig_replaced, …} | skeletal layer outcome (`zanatomy`: reference, re-skinned meshes, `body_match_max_mm`, …) |
| `files` | {usd, preview, skeleton_preview, metadata, textures[]} | relative file names |
| `warnings`, `notes` | [str] | problems / informational messages (e.g. missing asset packs) |
| `versions` | {blender, mpfb, generator, skeleton_layer} | software versions used |

Example (abridged, default `zanatomy` layer):

```json
{
  "schema_version": 1, "id": "H0001", "run_id": "run-20261018-211500", "seed": 67068514978558,
  "identity": {"sex": "female", "age_years": 77, "age_band": "71-85", "ethnicity": "south_asian",
               "race_mix": {"asian": 0.5752, "caucasian": 0.303, "african": 0.1218},
               "somatotype": "mesomorph_ectomorph", "skin_tone_mst": 6, "skin_rgb_hex": "#a07e56",
               "eye_color": "brown", "hair": {"style": "ponytail01", "color": "grey"}, "uniqueness_distance": null},
  "body": {"target_height_cm": 162.6, "height_cm": 162.96, "weight_kg": 48.8, "bmi": 18.4, "volume_l": 48.3, "fit_ok": true},
  "measurements_cm": {"stature_cm": 162.96, "ear_height_left_cm": 151.9, "c7_height_cm": 138.3, "...": "..."},
  "landmarks": {
    "T7": {"kind": "internal", "level": "T7", "ap_depth_m": 0.21, "internal_offset_m": 0.057,
           "bone": "LM_T7", "parent": "spine01", "rest_position_m": [0.0, 0.031, 1.243],
           "axes_xyz": [[0.0, -0.999, -0.038], [0.0, -0.038, 0.999], [-1.0, 0.0, 0.0]], "usd_joint": null},
    "tragus_L": {"kind": "anchor", "vertex": 12333, "bone": "LM_tragus_L", "parent": "head",
                 "rest_position_m": [0.069, -0.06, 1.52], "usd_joint": null}
  },
  "anatomy": {"source": "zanatomy", "reference_version": "zanatomy-ref-1", "count": 158, "bone_meshes": ["..."],
              "fit": {"landmark_residual_mm": {"median": 9.0, "p90": 30.0}, "bone_exposed_frac_approx": 0.022, "...": "..."},
              "points_m": {"hip_l": [0.09, -0.04, 0.93], "...": "..."}},
  "files": {"usd": "H0001.usd", "preview": "H0001.png", "metadata": "H0001.json", "skeleton_preview": null,
            "textures": ["H0001_eyebrows.png", "H0001_eyelashes.png", "H0001_feet.png", "H0001_full_body.png",
                         "H0001_hair.png", "H0001_skin.png"]},
  "versions": {"blender": "5.2.2 LTS", "mpfb": "2.0.18", "generator": "0.1.0", "skeleton_layer": "zanatomy-1"}
}

With `procedural` / `none` the `usd_joint` values are joint paths such as
`SkelOrigin/root/spine05/spine04/spine03/spine02/spine01/LM_T7`.
```

## 8.2 `population.csv`

One row per built human: `id, status, sex, age_years, age_band, ethnicity, somatotype,
skin_tone_mst, skin_rgb_hex, skin_albedo_hex, eye_color, clothing_variant, gown_color, target_height_cm, height_cm,
weight_kg, bmi, fit_ok, ear_height_left_cm, ear_height_right_cm, eye_height_cm, c7_height_cm,
shoulder_height_left_cm, jugular_notch_height_cm, xiphoid_height_cm, iliac_crest_height_cm,
chest_width_cm, chest_ap_depth_cm, biacromial_width_cm, landmark_joints, usd, preview, warnings`.

## 8.3 `summary.json`

```json
{
  "run_id": "run-…", "requested": 150, "status_counts": {"ok": 150}, "elapsed_s": 4512.3,
  "failed": {},
  "distributions": {
    "sex": {"configured_pct": {"male": 50, "female": 50}, "achieved": {"male": 75, "female": 75}},
    "ethnicity": {"...": "..."}, "age_band": {"...": "..."}, "somatotype": {"...": "..."},
    "clothing_variant": {"...": "..."}
  },
  "body_stats": {"height_cm": {"min": 146.1, "mean": 168.0, "max": 195.0}, "weight_kg": {}, "bmi": {}},
  "build_time_s": {"min": 22.1, "mean": 27.9, "max": 41.0}
}
```

## 8.4 `manifest.json`

```json
{"manifest_version": 1, "run_id": "run-…", "created": "…", "seed": 20261018, "count": 150,
 "humans": [ {"id": "H0001", "index": 0, "seed": 67068514978558, "sex": "female", "ethnicity": "south_asian",
              "age_band": "71-85", "somatotype": "mesomorph_ectomorph", "clothing_variant": "full_outfit",
              "age_years": 77, "target_height_cm": 162.6, "macros": {"...": "..."}, "skin": {"...": "..."},
              "face_targets": ["..."], "eyes": {"color": "brown"}, "hair": {"...": "..."},
              "eyebrows": "eyebrow001", "eyelashes": "eyelashes02", "gown_color": "green",
              "uniqueness_distance": null}, "…" ]}
```

The manifest holds the **inputs** of every human. Build outputs are in the per-human JSON.

## 8.5 `results.json`

Per human: `status` (ok / warn / failed), `height_cm`, `weight_kg`, `bmi`, `fit_ok`, `warnings`,
`notes`, `timings` (seconds per Blender build step), `duration_s`, `usd`, `log`, `skeleton_body`,
`usd_post`, `skeleton_layer` (layer, seconds, fit residuals), `validation` (see 07 §7.3), `animation`
(when written) and, for failures, `error` / `traceback`.
