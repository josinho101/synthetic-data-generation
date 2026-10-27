# 4. Metadata (`<id>.json`)

Same schema as the MPFB pipeline (`schema_version` 1) so `sdg` and the reports read both. Differences are marked.

| Key | Content |
|---|---|
| `id`, `run_id`, `created`, `seed` | |
| `identity` | sex, age_years, age_band (clipped band), ethnicity, race_mix, somatotype, skin tone (MST, hex), eye colour, hair, uniqueness_distance |
| `anny_phenotypes` *(MPFB: `mpfb_macros`)* | gender, age, muscle, weight, proportions, cupsize, firmness, race, solved height |
| `anny_local_changes` *(new)* | the face detail targets as Anny local changes (signed) |
| `face_targets` | sampled MakeHuman targets |
| `body` | target_height_cm, height_cm, weight_kg, bmi, volume_l, fit_ok, footwear_lift_cm, **height_scale** *(new)* |
| `measurements_cm` | stature, landmark heights, chest / abdomen width and AP depth, biacromial width |
| `appearance` | `skin` {source, texture, normal, roughness_map, tone {lab_before, lab_after}, roughness, subsurface}, `body_parts` |
| `clothing` | variant, `items[]` {slot, asset, object, color, hides_body, layer, poke_through_fixed_vertices, usd_prim} |
| `skeleton` | rig `anny_makehuman`, bone_count 375, deform_bone_count 163, landmark / frame counts, root_joint, USD prims |
| `landmarks` | 211 entries: kind, vertex (anchors), bone, parent, rest_position_m (world, after the footwear lift), usd_joint, axes_xyz, level |
| `spine_shape` | sampled kyphosis / lordosis / scoliosis, before / after |
| `anatomy` | bone_meshes[] {name, object, rig_bone, part, vertices, usd_prim}, count |
| `files` | usd, preview, metadata, textures |
| `usd_post` | clothing_holes, anatomy_purpose, root_joint |
| `warnings`, `notes`, `versions` | versions: anny, generator, python, device |

`sdg` reads `landmarks.T7.rest_position_m`, `body.height_cm`, `clothing.items[].asset` and
`skeleton.usd_skeleton_prim`.
