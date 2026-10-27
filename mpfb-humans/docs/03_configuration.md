# 3. Configuration reference

All configuration lives in `configs/`. Every run copies the YAML files to
`<run>/config_snapshot/` and writes the merged, validated configuration to
`<run>/resolved_config.json`, which is what the Blender workers read.

Rules that apply everywhere:

* **Percent blocks must sum to 100.** Counts are then allocated *exactly* (largest remainder).
* **Ranges** are `[min, max]` with `min ≤ max`. MPFB macro ranges lie in `0..1`.
* **Validation** runs before anything else (`sdg_humans/config/schema.py`). Errors are listed
  together, e.g. `population.sex: percentages must sum to 100 (got 110)`.
* **CLI overrides:** `--count`, `--seed`, `--workers` and `--output-root` override
  `population.count`, `population.seed`, `export.workers` and `export.output_root`.

---

## 3.1 `population.yaml`: who gets generated

| Key | Type | Default | Meaning |
|---|---|---|---|
| `count` | int ≥ 1 | 150 | number of humans |
| `seed` | int | 20261018 | global seed; each human gets `sha256(seed:index:attempt)` |
| `id_prefix`, `id_digits` | str, int | `H`, 4 | ids `H0001` … |
| `sex` | percent block | male 50 / female 50 | only `male`, `female` |
| `gender_macro.<sex>` | range 0..1 | male [0.9,1], female [0,0.1] | MPFB *gender* macro drawn per human (0 = female, 1 = male) |
| `female_macros.cupsize/firmness` | range | [0.3,0.8] | female breast macros (males use 0.5) |
| `age_bands` | percent block | 18-30:25, 31-50:35, 51-70:30, 71-85:10 | band names must be `lo-hi` years; age is uniform inside the band |
| `age_years_to_mpfb` | list of [years, macro] | [[1,0],[11,0.1875],[25,0.5],[90,1]] | piecewise-linear map to the MPFB *age* macro (MPFB: 25 y = 0.5, 90 y = 1.0) |
| `ethnicity` | percent block | 5 groups | each key needs a profile in `appearance.ethnicity_profiles` |
| `somatotype.<name>.pct` | percent | see file | share of the population |
| `somatotype.<name>.weight/muscle/proportions` | ranges 0..1 | see file | MPFB macros drawn uniformly per human |
| `bmi_guard` | [min,max] | [15, 45] | achieved BMI outside → `fit_ok=false`, warning |
| `body_density_kg_m3` | number | 1010 | mass = measured body volume × density |
| `height_cm.<sex>` | mean, sd, min, max | M 175±7.5 [155,200], F 162±7 [145,185] | truncated normal target stature |
| `height_cm.ethnicity_offset_cm` | map | e.g. east_asian −3 | added to the mean |
| `height_cm.tolerance_cm` | number | 0.5 | height solver stops within this tolerance |
| `height_cm.max_iterations` | int | 12 | bisection steps |
| `stratify_order` | list | sex, ethnicity, age_bands, somatotype, clothing | interleaving order: later strata are balanced *within* earlier ones |
| `uniqueness.min_feature_distance` | number | 0.08 | minimum identity distance to every earlier human |
| `uniqueness.max_resample` | int | 50 | redraws before accepting the most distinct candidate (warning) |

**Somatotypes and MPFB macros.** In MPFB, body fat comes from a **high weight macro combined with
low muscle**. weight 1 / muscle 0 is obese (BMI 33–39), while weight 1 / muscle 0.5 is only
BMI ≈ 22. The shipped ranges were calibrated with a macro grid scan (see
[05_body_and_identity.md](05_body_and_identity.md#somatotype--macros--bmi)).

Worked examples:

```yaml
# 70 % female, 30 % male
sex: {male: 30, female: 70}

# only adults 50+
age_bands: {"50-64": 60, "65-85": 40}

# heavier population
somatotype:
  endomorph:           {pct: 40, weight: [0.85, 1.00], muscle: [0.00, 0.20], proportions: [0.3, 0.5]}
  endomorph_mesomorph: {pct: 30, weight: [0.75, 1.00], muscle: [0.55, 0.90], proportions: [0.4, 0.6]}
  mesomorph:           {pct: 30, weight: [0.50, 0.75], muscle: [0.75, 1.00], proportions: [0.5, 0.7]}
```

---

## 3.2 `appearance.yaml`: how humans look

| Key | Type | Meaning |
|---|---|---|
| `ethnicity_profiles.<eth>.race_mix` | {asian, caucasian, african} | MPFB race macros, normalised to sum 1 |
| `…jitter` | number | ± uniform noise per race component before normalising |
| `…base_skin` | asian / caucasian / african | which MakeHuman system skin to use (packs only) |
| `…skin_tone_weights` | {MST level: weight} | Monk Skin Tone levels (1 lightest … 10 darkest) and their relative weights |
| `skin_tones_rgb` | {1..10: "#rrggbb"} | Monk reference colour per level (perceived colour; reported in metadata, **not** used as texture colour) |
| `skin_albedo_lab` | {1..10: [L*, a*, b*]} | skin **albedo** per Monk level; the skin texture is matched to it (L* 71 for MST 1 … 28 for MST 10). Raise / lower L* to make a level lighter / darker |
| `skin.source` | auto / layered / mhmat | `mhmat` = MakeHuman photo skins (realistic, needs packs); `layered` = MPFB procedural skin (flat, no packs); `auto` (default) = mhmat if installed |
| `skin.dark_texture_from_mst` | int or null | Monk level from which the dark-skinned photo texture is used (7); null = always the ethnicity's `base_skin` |
| `skin.tone_match_strength` | 0–1 | 1 = texture median matched exactly to `skin_albedo_lab`; 0 = raw photo colour |
| `skin.tone_jitter` | number | ± relative lightness jitter (on L*) so equal levels still differ |
| `skin.bake_resolution` | int | albedo texture size baked for USD (2048) |
| `skin.roughness` | number | Principled roughness of the exported skin |
| `skin.age_variant` | {young/middleage/old: [lo, hi] years} | selects the system skin by age |
| `face.symmetric` | bool | same value on left and right for sided targets |
| `face.sections.<section>` | [min_picks, max_picks, deviation] | per MPFB target section: pick count and magnitude (see 05) |
| `eyes.colors` | percent block | eye colour distribution |
| `eyes.rgb` | {colour: hex} | iris colour for generated eyes |
| `hair.<sex>.styles` | {name: weight} | installed hair asset (afro01, bob01, bob02, braid01, long01, ponytail01, short01–04) or `none` |
| `hair.colors`, `hair.rgb` | {name: weight}, {name: hex} | hair colour distribution; tint applied to hair and eyebrows |
| `eyes.source` | generated / pack | generated eyes use `eyes.colors`; `pack` uses the MakeHuman eye mesh |
| `hair.grey_from_age` | years | grey probability rises linearly to 100 % at 85 |
| `eyebrows.pool`, `eyelashes.pool` | list | asset name substrings |

Face sections available in MPFB 2.0.18: `nose, chin, eyes, mouth, ears, cheek, forehead, head,
eyebrows, neck` (also `arms, legs, torso, hip, stomach, …` for body details).

Add an ethnicity:

```yaml
# population.yaml
ethnicity: {east_asian: 15, south_asian: 15, african: 20, caucasian: 25, hispanic_latino: 15, middle_eastern: 10}
# appearance.yaml
ethnicity_profiles:
  middle_eastern:
    race_mix: {asian: 0.15, caucasian: 0.75, african: 0.10}
    jitter: 0.08
    base_skin: caucasian
    skin_tone_weights: {3: 25, 4: 35, 5: 30, 6: 10}
# and an ethnicity_offset_cm entry in population.yaml (optional)
```

---

## 3.3 `clothing.yaml`: what humans wear

| Key | Meaning |
|---|---|
| `enabled` | `true` (default) dresses every human with its variant. `false` generates all humans **unclothed**: no garments and no shoes (barefoot on the floor, no `hide_body_under` cut), `variants` / `fallback_variant` are ignored, `clothing.variant` is `none` and the body mesh gets no clothing `holeIndices` |
| `variants.<name>.pct` | share of the population (exact quota) |
| `variants.<name>.slots.<slot>.asset` | fixed MHCLO file (relative to `assets/` or absolute) |
| `variants.<name>.slots.<slot>.garment` | an ID from `garment_catalog.yaml` (e.g. `L06`); the installed asset of that name is used. A missing asset follows `fallback_if_missing` like a fixed `asset:` |
| `variants.<name>.slots.<slot>.mpfb_slot` | keyword pick from installed MPFB clothes: `chance` (0–100), `include_any`, `include_male`, `include_female`, `exclude`, `pack` (comma-separated, case-insensitive substrings). Same semantics as MPFB's own randomizer slots. |
| `variants.<name>.slots.<slot>.male` / `.female` | a different slot per sex; a sex without an entry gets no garment in that slot (e.g. skirts only for women) |
| `variants.<name>.slots.<slot>.one_of` | list of alternative slots with `weight`; one is picked per human |
| `variants.<name>.slots.<slot>.recolor` | palette name in `garment_colors`; the garment gets a random colour from it (texture shading and details such as buttons are kept) |
| `garment_colors.<palette>.<colour>` | `pct` (weight) and `rgb` (`#rrggbb`) |
| `mpfb_packs` | restrict all `mpfb_slot` picks to these pack names |
| `gown_colors.<name>` | `pct`, `rgb`, `pattern` (`stripes` = vertical `rgb` stripes on `base_rgb`; `solid` = whole gown `rgb`), `base_rgb` (background and sleeve trim) |
| `gown_thickness_cm` | solidify thickness (double-sided look in Isaac Sim) |
| `gown_shaping.smooth_iterations / smooth_factor` | build-time Smooth modifier that relaxes the fitted gown |
| `gown_shaping.inflate_cm` | outward push after smoothing (prevents skin poke-through) |
| `gown_shaping.edge_rings` | smoothing fades to 0 over this many edge rings at cut edges (keeps hems in place) |
| `subdiv_levels` | subdivision on clothes (0 recommended) |
| `remove_hidden_body_faces` | keep `false`: the body under clothes is needed for landmarks |
| `fallback_if_missing` | `skip_slot` (warn and continue) or `error` (fail the human) for a missing fixed asset |
| `fallback_variant` | variant used when a variant yields no garment at all (e.g. no clothes packs) |
| `hide_body_under` | slots whose garment hides the body underneath (removed at export; default `[feet]`) |
| `garment_texture_max_px` | resolution limit of baked garment textures |
| `poke_through_clearance_cm` | garment vertices closer than this to the skin (or inside it) are pushed out after fitting, so no skin shows through tight clothes on full bodies; the body itself stays complete (0 = off) |
| `poke_through_max_edge_cm` | garment edges near the skin are first split to this length, so coarse garments cannot cut through curved body parts between their vertices |
| `layer_offset_cm` | the outer garment of a top + bottom pair is pushed out by this (trousers over tucked shirts, otherwise top over bottom) |
| `gown_shaping.weight_smooth_iterations / weight_smooth_below` | blended skin weights on the lower gown (natural sway when animated) |

Shipped variants (garments by catalogue ID, see 3.3a and `output/garment_catalog/`):

| Variant | % | Men | Women |
|---|---|---|---|
| `full_outfit` | 50 | F01, F03 or F06 (casual suits) | F09 (casual suit) or F11 (elegant suit) |
| `top_and_jeans` | 50 | U07 polo (recoloured from `garment_colors.shirt`) + L03 classic jeans | U13 or U14 sweater + L04 tight jeans |

Shoes, equal chance per sex: men S01, S03, S08, S11, S25; women S02, S06, S07, S10, S14, S18.
A full outfit is one mesh for top and bottom, so it is removed as a whole. The YAML anchor `_shoes` keeps the
shoe lists in one place. The chosen garments and colours are recorded per human in
`H0001.json → clothing.items` (`asset`, `color`). The hospital gowns and the office skirt are still generated
(`gown.yaml`) and can be added back as `asset:` slots.

Add a variant (requires installed MPFB clothes packs):

```yaml
variants:
  scrubs:
    pct: 10                   # take 10 from another variant so the block still sums to 100
    slots:
      upper_body: {mpfb_slot: {include_any: "scrub,tshirt"}}
      lower_body: {mpfb_slot: {include_any: "scrub,pants"}}
```

Or pick garments by catalogue ID (see 3.3a):

```yaml
  knit_and_trousers:
    pct: 10
    slots:
      upper_body: {one_of: [{weight: 50, garment: U14}, {weight: 50, garment: U15}]}
      lower_body: {male: {garment: L06}, female: {garment: L08}}
      feet: {male: {garment: S01}, female: {garment: S02}}
```

## 3.3a `garment_catalog.yaml`: garment IDs

Every installed MPFB / MakeHuman clothes asset has a stable ID: `U` upper body, `L` lower body, `F` full outfit
(one mesh for top and bottom, removed as a whole), `S` shoes, `H` hats. Each entry holds `asset` (asset name),
`category`, `sex` (`male` / `female` / `any`), `rating` and `maps` (the asset's texture maps), plus optional `notes`.

| Rating | Meaning |
|---|---|
| A | realistic, PBR maps (normal / specular / AO) |
| B | plausible, diffuse-only or low resolution (looks flatter) |
| C | low quality (very low poly, "crude") |
| X | costume / fantasy / print or logo: not for clinical SDG |

The ratings were first set from the asset metadata. Check them visually with the catalogue renderer, which dresses
one reference male and one reference female (the first of each in a 10-human sample) with every garment, one at
a time, and renders front + side with Cycles on the GPU (about 10 s per tile):

```bash
.venv/bin/python scripts/garment_catalog.py                    # all -> output/garment_catalog/
.venv/bin/python scripts/garment_catalog.py --ids U14 L06 S01  # only these
.venv/bin/python scripts/garment_catalog.py --category shoes --out /tmp/cat
```

Output: `tiles/<ID>_<sex>.png`, `catalog_<category>.png` sheets labelled `ID [rating] sex asset`, `catalog.png`
(all) and `index.csv`. Garments render with their own MakeHuman material (normal / specular maps included), i.e.
the asset at its best. The built humans currently keep only the diffuse map.

## 3.4 `gown.yaml`: gown generator

| Key | Default | Meaning |
|---|---|---|
| `output_dir` | `assets/custom/hospital_gown` | where the gown assets are written |
| `variants.<name>.length` / `.sleeve` | | keys of `lengths` / `sleeve_ends` |
| `variants.<name>.looseness_cm` | 2.0 | clearance of shell and drape |
| `variants.<name>.back_opening` | true | open back strip + ties |
| `lengths` | mid_thigh 0.5, knee 1.0, above_knee 0.9 | hem height as a fraction from the hip joint (0) to the knee joint (1) |
| `variants.office_skirt` | `type: skirt` | knee-length pencil skirt: `length`, `looseness_cm` (0.8), `waist_above_hip_cm` (10, waistband height above the hip joints), `taper_cm_per_m` (2, narrowing towards the hem) |
| `sleeve_ends` | short 0.5, elbow 1.0 | sleeve end as a fraction from the shoulder joint to the elbow joint |
| `sleeve_widen_cm`, `sleeve_trim_fraction` | 2.0, 0.12 | sleeve opening width; part of the sleeve mapped to the white trim |
| `neckline_drop_front_cm`, `neckline_drop_back_cm` | 4, 2 | round neckline below the neck joint |
| `shell_smooth_iterations` | 12 | smoothing of the upper shell |
| `seam_below_armpit_cm`, `seam_cover_cm` | 12, 0.4 | how far the shell reaches below the armpits; its clearance over the drape |
| `armpit_drop_cm`, `tube_top_below_armpit_cm` | 7, 3 | armpit level below the shoulder joints; drape start |
| `flare_cm_per_m` | 6 | A-line flare of the drape |
| `segments_around`, `ring_spacing_cm` | 64, 1.5 | drape resolution |
| `back_opening_width_cm`, `tie_heights` | 4, [0.35, 0.65] | open strip width; tie positions (fraction shoulders → hips) |
| `stripe_repeats_around`, `texture_size`, `author`, `license` | 16, 512 | texture tiling and MHCLO metadata |

After editing `gown.yaml` run `scripts/make_gown.py` again.

## 3.5 `landmarks.yaml`: anatomical landmarks

| Key | Meaning |
|---|---|
| `anchors.<name>` | basemesh vertex ID (same topology on every human). `null` = not calibrated |
| `spine.levels` | vertebra names, cranial → caudal |
| `spine.segment_ratios.<level>` | relative height of each vertebra + disc |
| `spine.pins` | levels that sit exactly on an anchor (C7, T12, L4, S1) |
| `spine.top_anchor` / `bottom_anchor` | boundaries above C1 / below S5 (inion, coccyx) |
| `spine.top_offset_cm` | C1 starts this far below the inion |
| `spine.internal_depth.<C/T/L/S>` | `fraction` of the local antero-posterior depth (ray cast) **or** `fixed_cm` (+ `scale_with_stature`) |
| `spine.emit` | `internal` (vertebral body, `LM_T7`) and/or `surface` (skin over the spinous process, `LM_T7_surf`) |
| `spine.max_forward_cm` | posterior profile points may lie at most this far in front of the anchor chain |
| `parent_bones` | landmark → MPFB default-rig bone. Ranges (`T1-T4`) and `{side}` (L/R) expand |
| `bone_prefix`, `bone_length_m` | joint naming (`LM_`) and display length |
| `heights_from_landmarks` | landmark → metadata key for heights above the floor (e.g. `tragus_L: ear_height_left_cm`) |

Add a landmark, e.g. the 7th rib tip on the left: add `rib7_L: <vertex id>` under `anchors`
(find the ID in Blender, see 06), add `rib7_{side}: spine04` under `parent_bones`, and optionally
`rib7_L: rib7_height_cm` under `heights_from_landmarks`.

## 3.6 `export.yaml`: runtime, environment, USD

| Key | Default | Meaning |
|---|---|---|
| `output_root` | `…/synthetic-data-generation/output/humans` | each run → `<output_root>/run-<timestamp>/` |
| `run_dir_format` | `run-%Y%m%d-%H%M%S` | strftime format of the run folder |
| `blender_bin` | `/snap/bin/blender` | Blender executable |
| `min_python`, `min_blender`, `tested_blender`, `min_mpfb` | 3.10 / 4.2.0 / 5.2 / 2.0.18 | preflight version rules |
| `mpfb_module`, `mpfb_data_dir` | auto | override MPFB detection |
| `asset_mode` | auto | `required` → preflight fails when asset packs are missing |
| `asset_packs` | 7 packs | MakeHuman packs to install: `{name, file, license}` (see [02 §2.4](02_setup.md#24-makehuman-asset-packs-hair-skins-garments)) |
| `asset_packs_url` | `https://files2.makehumancommunity.org/asset_packs` | download URL = `<url>/<name>/<file>` |
| `asset_packs_download_dir` | `~/.cache/sdg_asset_packs` | cache of downloaded zips |
| `asset_packs_target` | auto | install folder (auto = MPFB user data dir) |
| `install_missing_packs` | false | `true` = every run downloads + installs missing packs (like `--install-packs`) |
| `workers` | 1 | parallel Blender processes (each ~1.5 GB RAM; GPU bake shared) |
| `timeout_s_per_human`, `retries` | 1200, 1 | per-human timeout and extra attempts |
| `est_mb_per_human` | 60 | free-disk check |
| `usd.file_format` | usd | `usd` (binary crate), `usda` (text, large), `usdc` |
| `usd.meters_per_unit`, `usd.up_axis` | 1.0, Z | stage metadata (Isaac Sim default: meters, Z-up) |
| `usd.triangulate` | false | triangulate meshes before export |
| `usd.max_bone_influences` | 4 | weights per vertex (limited + normalised) |
| `usd.export_textures`, `usd.relative_paths` | true | textures referenced relatively from `textures/` |
| `usd_post.enabled` | true | post-export fixes on the USD (`sdg_humans/usd_post.py`, see [07 §7.2a](07_usd_isaac_sim.md#72a-post-export-fixes-usd_post)) |
| `usd_post.clothing_holes` | true | body faces fully covered by garments become `holeIndices` of the body mesh (not rendered), so skin cannot poke through the clothes when the human moves; points and topology stay complete |
| `usd_post.clothing_min_covered_fraction` | 0.75 | a face is hidden when this share of its vertices **and** its centre are covered: faces under openings (collar placket, open-back gown) stay, faces at sleeve ends / armpits that push out of crumpled sleeves are hidden |
| `usd_post.clothing_reach_cm` | 7 | skin counts as covered when cloth lies within this distance outside it (loose sleeves, gowns) |
| `usd_post.anatomy_purpose` | guide | purpose of the `bone_*` anatomy meshes: `guide` = kept in the file, not rendered (rigidly skinned, they poke through the skin in strong poses); `default` = rendered |
| `usd_post.root_joint` | SkelOrigin | identity root joint inserted above MPFB's `root` (pelvis) for retargeting (Isaac Sim behavior agents); `null` = MPFB skeleton unchanged. Must not be `root` in any case |
| `preview.resolution` | [512, 768] | per view; front + left side side by side |
| `preview.engines` | EEVEE, EEVEE_NEXT, WORKBENCH | first available engine is used |
| `preview.background_rgb`, `preview.samples` | grey, 16 | render look / speed |
| `preview.landmark_overlay` | false | also write `<id>_landmarks.png` with landmark dots (QA; off by default) |
| `animation.enabled` | false | also write the animated Isaac Sim scene `<id>_anim.usda` next to `<id>.usd` ([isaac/README.md](../isaac/README.md)); `fps`, `walk_distance_m`, `walk_speed_mps`, `jump_height_m` shape it |
| `bake.device` | auto | `auto` / `GPU` / `CPU` for the Cycles texture bake |
| `bake.samples`, `bake.margin_px` | 4, 8 | bake quality / UV island padding |

## 3.7 `anatomy.yaml`

Anatomical skeleton options; see [11_anatomy.md](11_anatomy.md#113-configuration-configsanatomyyaml).

## 3.8 `logging.yaml`

See [09_logging_and_monitoring.md](09_logging_and_monitoring.md).

| Key | Meaning |
|---|---|
| `keep_last_runs` | number of central `logs/run-*.log` copies kept |
| `worker_level`, `worker_format` | level (default INFO) and format of the per-human Blender logs |
| `dict_config` | standard `logging.config.dictConfig`; `{run_dir}` is substituted |
