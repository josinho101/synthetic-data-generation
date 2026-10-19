# 6. Landmarks

## 6.1 What you get

Every human's skeleton contains **84 extra joints** (prefix `LM_`), non-deforming children of
the MPFB default rig bones:

| Group | Joints | Parent bones |
|---|---|---|
| Vertebral bodies (internal) | `LM_C1 … LM_C7`, `LM_T1 … LM_T12`, `LM_L1 … LM_L5`, `LM_S1 … LM_S5` | nearest axial bone (`auto_axial`) |
| Spinous processes on the skin (surface) | `LM_C1_surf … LM_S5_surf` | same as the vertebra |
| Spine anchors | `LM_inion`, `LM_c7_spinous`, `LM_t12_spinous`, `LM_l4_spinous`, `LM_s1_spinous`, `LM_coccyx` | head / neck03 / spine03 / spine01 / root |
| Head | `LM_vertex`, `LM_nasion`, `LM_chin`, `LM_tragus_L/R` (ear height), `LM_outer_canthus_L/R` (eye height) | head, jaw |
| Trunk | `LM_jugular_notch`, `LM_xiphoid`, `LM_navel` | spine05, spine04, spine02 |
| Shoulder / pelvis / legs | `LM_acromion_L/R`, `LM_asis_L/R`, `LM_iliac_crest_L/R`, `LM_greater_trochanter_L/R`, `LM_heel_L/R` | shoulder01, pelvis, upperleg01, foot |

Because they are joints, a posed or animated skeleton in Isaac Sim moves them with the body. Their
world positions per frame give the annotations (see [07](07_usd_isaac_sim.md#76-reading-landmarks-in-isaac-sim)).
Rest positions, parents and USD joint paths are also stored in `H0001.json → landmarks`.

## 6.2 Anchors: one vertex ID for every human

All MPFB humans share **one base-mesh topology** (13 380 body vertices). Macros and targets move
vertices but never renumber them. A vertex ID chosen once on the neutral human therefore marks the
same anatomical point on all 150 humans, whatever their shape. These IDs are the `anchors` in
`landmarks.yaml`.

### Auto calibration (`scripts/calibrate_anchors.py --auto`)

`sdg_humans/blender/calibrate.py` builds the neutral human and applies rules relative to MPFB's
**joint cubes** (`joint-neck`, `joint-head`, `joint-spine-1..4`, `joint-l-upper-leg`, …).
Front = −Y, back = +Y, left = +X:

| Anchor | Rule |
|---|---|
| inion | posterior-most midline vertex at `joint-head.z + 1 cm` |
| c7_spinous | posterior midline at `joint-neck.z − 2 cm` (vertebra prominens) |
| t12_spinous | posterior midline at `joint-spine-2.z + 1.5 cm` |
| l4_spinous | posterior midline at mid-height of `joint-spine-3/4` (intercristal line) |
| s1_spinous | posterior midline at `joint-spine-4.z − 3 cm` (PSIS level) |
| coccyx | posterior midline at hip-joint height − 3 cm |
| vertex | highest midline vertex |
| nasion | anterior midline at eye-centre height + 0.8 cm |
| chin | lowest anterior midline vertex between neck and mouth |
| jugular_notch | anterior midline at clavicle-joint height + 1 cm |
| xiphoid | anterior midline at `joint-spine-1.z − 4 cm` |
| navel | deepest anterior midline point between `joint-spine-4` and `joint-spine-2` |
| tragus_L/R | most anterior vertex of the `ears` vertex group at mid ear height |
| outer_canthus_L/R | body vertex closest to the lateral-most eye-helper vertex |
| acromion_L/R | vertex within 9 cm of the shoulder joint maximising `z + 0.5·|x|` |
| asis_L/R | most anterior vertex at hip-joint height + 7.5 cm, ~0.85 × hip-joint x |
| iliac_crest_L/R | most lateral torso vertex at L4 height |
| greater_trochanter_L/R | most lateral torso vertex at hip-joint height |
| heel_L/R | most posterior foot vertex below 5 cm |

### Refining an anchor by hand

1. In Blender: MPFB sidebar → *New human* → *Create human* (neutral).
2. Edit Mode → select the vertex you want → enable *Developer Extras* (Preferences → Interface) and
   *Indices* in the overlay, or run `bpy.context.object.data.vertices.foreach_get` in the Python
   console to read the selected index.
3. Write the index into `landmarks.yaml → anchors.<name>`.
4. Rebuild a test human and inspect `<id>_landmarks.png`.

## 6.3 Vertebrae

Only C7, T12, L4 and S1 are pinned to anchors. The other 25 levels are interpolated **per human**
along that human's own back:

1. **Posterior midline profile** (`landmark_math.posterior_profile`): body vertices with
   |x| < 6 mm, binned every 1 cm in z, taking the most posterior vertex per bin. A point is only
   accepted if it lies at most `max_forward_cm` (4 cm) in front of the anchor chain
   inion → C7 → T12 → L4 → S1 → coccyx, so throat, chin or belly vertices can never be mistaken
   for the back.
2. **Arc positions:** the anchors are projected onto the profile polyline (arc length `s`). C1
   starts `top_offset_cm` (2 cm) below the inion and S5 ends at the coccyx.
3. **Ratio distribution** (`landmark_math.distribute_levels`): between two known points `a` and `b`
   the free levels are placed at
   `s_i = s_a + (s_b − s_a) · (½r_a + Σ r_before_i + ½r_i) / (½r_a + Σ r_between + ½r_b)`,
   where `r` are the `segment_ratios` (relative vertebra + disc heights, growing from C3 to L3) and
   a boundary (not a level) contributes 0.
4. **Surface point** = profile point at `s_i` (`LM_<level>_surf`).
5. **Internal point** (vertebral body centre, `LM_<level>`) = surface point moved anteriorly (−Y):
   * T, L, S: `fraction × AP depth`, where AP depth is the distance from the back surface to the
     next body surface along −Y (BVH ray cast). Fractions: T 0.27, L 0.30, S 0.22.
   * C: fixed 4.5 cm × stature/170 cm. A forward ray from the neck hits the jaw or mouth cavity,
     which makes the depth unreliable.

## 6.4 Parent bones (`auto_axial`)

MPFB numbers its spine bones **from the top**: `spine01` is the upper chest and `spine05` sits just
above the pelvis (`root`). With `parent_bones: auto_axial` (default for all spine levels, spine
anchors, jugular notch, xiphoid and navel), each landmark is parented per human to the bone of the
chain `root → spine05 → … → spine01 → neck01–03 → head` whose segment is closest to it. Thoracic
landmarks therefore follow the chest bones and lumbar landmarks the lower spine when the human bends
or walks. The bone meshes (vertebrae, ribs, sternum) use the same parents.

## 6.5 QA image

With `preview.landmark_overlay: true`, each human gets `<id>_landmarks.png`: front and side views
with **red** = internal vertebrae, **yellow** = surface vertebrae, **cyan** = anchors. Check that:
red lies inside the body in front of yellow, both run C1 → S5 top to bottom, and the cyan points sit
on the ears, shoulders, pelvis and heels.

## 6.6 Accuracy and limits

* Landmarks are **anthropometric estimates from the body surface**, not CT/MRI-derived anatomy.
  Vertebral levels follow population-average segment proportions between four pinned levels.
* Pinned levels inherit the anchor rules above; expect ±1 vertebral level of uncertainty in the
  mid-thoracic region and ±1–2 cm in internal depth.
* The rest pose is MPFB's A-pose; posture variations (kyphosis, scoliosis) are not modelled.
* For higher fidelity, replace the rules with vertex IDs selected by a radiologist on the neutral
  mesh (§6.2), or adjust `segment_ratios` / `internal_depth`.

## 6.7 Adding a landmark

1. `anchors.my_point: <vertex id>`
2. `parent_bones.my_point: spine04` (or `my_point_{side}: "clavicle.{side}"` with `_L`/`_R` anchors)
3. optional `heights_from_landmarks.my_point: my_point_height_cm`

The new joint `LM_my_point` appears in the USD, in the metadata and in the overlay.
