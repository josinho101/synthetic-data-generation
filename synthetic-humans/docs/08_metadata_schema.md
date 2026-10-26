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
| `measurements_cm.<key>` | float | heights above the floor from `landmarks.heights_from_landmarks`: `vertex_height_cm`, `ear_height_left_cm`, `ear_height_right_cm`, `nasion_height_cm`, `eye_height_cm`, `chin_height_cm`, `c7_height_cm`, `shoulder_height_left_cm`, `shoulder_height_right_cm`, `jugular_notch_height_cm`, `xiphoid_height_cm`, `navel_height_cm`, `iliac_crest_height_cm`, `asis_height_cm`, `trochanter_height_cm` |
| `measurements_cm.chest_width_cm`, `chest_ap_depth_cm` | float | at xiphoid height; arm vertices excluded by their dominant rig bone |
| `measurements_cm.abdomen_width_cm`, `abdomen_ap_depth_cm` | float | at navel height |
| `measurements_cm.biacromial_width_cm` | float | acromion to acromion |
| `appearance.skin` | {source, texture} | `layered` or `mhmat:<file>`, baked texture name |
| `appearance.body_parts` | {eyes, eyebrows, eyelashes, hair} | asset used, `generated`, or null |
| `clothing.variant`, `clothing.gown_color` | str | variant `none` when `clothing.enabled` is false |
| `clothing.items` | [{slot, asset, object, variant}] | garments actually worn |
| `skeleton.rig`, `bone_count`, `deform_bone_count`, `landmark_joint_count` | | `mpfb_default`, 247, 163, 84 |
| `skeleton.usd_root_prim`, `skeleton.usd_skeleton_prim` | str | `/H0001`, `/H0001/H0001_rig/H0001_rig` |
| `landmarks.<name>.kind` | anchor / surface / internal | |
| `landmarks.<name>.level` | str | vertebra level (spine points) |
| `landmarks.<name>.vertex` | int | basemesh vertex (anchors) |
| `landmarks.<name>.rest_position_m` | [x, y, z] | rest pose, stage meters (feet at z = 0, facing −Y) |
| `landmarks.<name>.ap_depth_m`, `internal_offset_m` | float | internal points: local AP depth and offset used |
| `landmarks.<name>.bone`, `parent`, `usd_joint` | str | Blender bone, parent bone, full UsdSkel joint path |
| `anatomy.count`, `anatomy.bone_meshes[]` | | bone meshes: `name`, `object`, `rig_bone`, `part`, `vertices`, `usd_prim` (doc 11) |
| `files` | {usd, preview, skeleton_preview, metadata, textures[]} | relative file names |
| `warnings`, `notes` | [str] | problems / informational messages (e.g. missing asset packs) |
| `versions` | {blender, mpfb, generator} | software versions used |

Example (abridged):

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
           "bone": "LM_T7", "parent": "spine04", "rest_position_m": [0.0, 0.031, 1.243],
           "usd_joint": "root/spine05/spine04/LM_T7"},
    "tragus_L": {"kind": "anchor", "vertex": 12333, "bone": "LM_tragus_L", "parent": "head",
                 "rest_position_m": [0.069, -0.06, 1.52], "usd_joint": "root/…/head/LM_tragus_L"}
  },
  "files": {"usd": "H0001.usd", "preview": "H0001.png", "metadata": "H0001.json",
            "textures": ["H0001_gown.png", "H0001_skin.png"]},
  "versions": {"blender": "5.2.2 LTS", "mpfb": "2.0.18", "generator": "0.1.0"}
}
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
              "age_band": "71-85", "somatotype": "mesomorph_ectomorph", "clothing_variant": "gown",
              "age_years": 77, "target_height_cm": 162.6, "macros": {"...": "..."}, "skin": {"...": "..."},
              "face_targets": ["..."], "eyes": {"color": "brown"}, "hair": {"...": "..."},
              "eyebrows": "eyebrow001", "eyelashes": "eyelashes02", "gown_color": "green",
              "uniqueness_distance": null}, "…" ]}
```

The manifest holds the **inputs** of every human. Build outputs are in the per-human JSON.

## 8.5 `results.json`

Per human: `status` (ok / warn / failed), `height_cm`, `weight_kg`, `bmi`, `fit_ok`, `warnings`,
`notes`, `timings` (seconds per build step), `duration_s`, `usd`, `log`, `validation` (see 07 §7.3)
and, for failures, `error` / `traceback`.
