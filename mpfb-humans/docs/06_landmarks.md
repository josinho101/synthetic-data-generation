# 6. Landmarks

## 6.1 What you get

Every human gets **211 landmarks** in `<id>.json → landmarks`: **175 points** (prefix `LM_`) and
**36 oriented frames** (prefix `AN_`), built from 74 anchor vertices. The table below is the base
set (128 `LM_` + 5 `AN_`); §6.8 lists the derived joints that make up the rest. The MHR pipeline
(`mhr-synthetic-human`) emits the same joints with the same names, from the same rules
(`sdg_humans/landmark_rules.py` is shared verbatim).

**Joints or data.** In the Blender build every landmark is a non-deforming child bone of the MPFB
default rig. Whether they stay joints in the USD depends on the skeletal layer
([14](14_skeleton_layer.md)):

* `procedural` / `none`: they are USD joints (`usd_joint` in the JSON) and follow any animation;
* `zanatomy` (default): the rig is replaced by the anatomical rig and the landmarks are **data only**
  (`usd_joint: null`), unless `keep_landmark_joints: true`. The fitted bony landmarks and joint
  centres of the Z-Anatomy skeleton are in `<id>.json → anatomy.points_m`.

| Group | Joints | Parent bones |
|---|---|---|
| Vertebral bodies (internal, **oriented**) | `LM_C1 … LM_C7`, `LM_T1 … LM_T12`, `LM_L1 … LM_L5`, `LM_S1 … LM_S5` | nearest axial bone (`auto_axial`) |
| Spinous processes on the skin (surface) | `LM_C1_surf … LM_S5_surf` | same as the vertebra |
| Spine anchors | `LM_inion`, `LM_c7_spinous`, `LM_t7_spinous`, `LM_t12_spinous`, `LM_l4_spinous`, `LM_s1_spinous`, `LM_coccyx` | head / `auto_axial` / root |
| Head | `LM_vertex`, `LM_glabella`, `LM_nasion`, `LM_chin`, `LM_tragus_L/R`, `LM_outer_canthus_L/R`, `LM_infraorbital_L/R` (orbitale), `LM_mastoid_L/R`, `LM_gonion_L/R` | head, jaw |
| Trunk | `LM_jugular_notch`, `LM_sternal_angle`, `LM_xiphoid`, `LM_costal_margin_L/R`, `LM_navel`, `LM_pubic_symphysis` | `auto_axial`, root |
| Shoulder girdle | `LM_acromion_L/R`, `LM_coracoid_L/R`, `LM_scapula_superior_angle_L/R`, `LM_scapula_spine_root_L/R`, `LM_scapula_inferior_angle_L/R` | shoulder01 |
| Pelvis / hip | `LM_asis_L/R`, `LM_psis_L/R`, `LM_iliac_crest_L/R`, `LM_greater_trochanter_L/R` | pelvis, upperleg01 |
| Upper limb | `LM_lateral_epicondyle_L/R`, `LM_medial_epicondyle_L/R`, `LM_olecranon_L/R`, `LM_radial_styloid_L/R`, `LM_ulnar_styloid_L/R` | upperarm02, lowerarm01, lowerarm02 |
| Lower limb | `LM_patella_L/R`, `LM_lateral_femoral_epicondyle_L/R`, `LM_medial_femoral_epicondyle_L/R`, `LM_fibular_head_L/R`, `LM_lateral_malleolus_L/R`, `LM_medial_malleolus_L/R`, `LM_heel_L/R` | upperleg02, lowerleg01/02, foot |
| Anatomical frames (**oriented**) | `AN_skull` (Frankfort plane), `AN_thorax`, `AN_pelvis`, `AN_scapula_L/R` (ISB definitions) | head, spine02, root, shoulder01 |

**Oriented joints.** `AN_*` frames and the vertebral bodies `LM_C1 … LM_S5` carry a meaningful
rotation: joint axes **X anterior, Y superior, Z subject right** (ISB-style, the same directions
on both sides). Vertebral bodies have Y along the spine curve, so their tilt follows the spine in
any pose. All other `LM_*` joints are position-only (axes aligned with the world at rest).

| Frame | Origin | Axes |
|---|---|---|
| `AN_skull` | mid-tragion | Z tragus_L → tragus_R; X towards mid-orbitale (Frankfort horizontal) |
| `AN_thorax` | jugular notch | Y from mid(xiphoid, T8) to mid(jugular notch, C7); Z normal to that sagittal plane |
| `AN_pelvis` | mid-ASIS | Z ASIS_L → ASIS_R; X from mid-PSIS to mid-ASIS |
| `AN_scapula_L/R` | acromion | Z along the scapular spine (spine root ↔ acromion, towards the right); X normal to the scapular plane |

Where they are joints, a posed or animated skeleton in Isaac Sim moves them with the body, and their
world positions per frame give the annotations (see [07](07_usd_isaac_sim.md#76-reading-landmarks-in-isaac-sim)).
Rest positions, parents and USD joint paths (or `null`) are stored in `H0001.json → landmarks`.

## 6.2 Anchors: one vertex ID for every human

All MPFB humans share **one base-mesh topology** (13 380 body vertices). Macros and targets move
vertices but never renumber them. A vertex ID chosen once on the neutral human therefore marks the
same anatomical point on all 150 humans, whatever their shape. These IDs are the `anchors` in
`landmarks.yaml`.

### Auto calibration (`scripts/calibrate_anchors.py --auto`)

`sdg_humans/blender/calibrate.py` builds the neutral human and runs `landmark_rules.propose_anchors`
(numpy only, identical in the MHR pipeline). MPFB's **joint cubes** give the reference joint
centres (hip, knee, ankle, shoulder, elbow, wrist, eye, thumb and little-finger base). Front = −Y,
back = +Y, left = +X; distances scale with stature (`k = stature / 1.70 m`).

| Anchors | Rule |
|---|---|
| spinous anchors, coccyx | posterior-most midline vertex at a stature fraction: C7 0.838, T7 0.745, T12 0.670, L4 0.590, S1 0.556, coccyx 0.509 |
| jugular notch, sternal angle, xiphoid | anterior-most midline vertex at 0.813 / 0.783 / 0.723 of stature |
| navel | deepest anterior midline point between 0.575 and 0.650 of stature (0.600 if the mesh has no dimple) |
| pubic symphysis | anterior midline at 0.515 of stature |
| vertex, inion, nasion, glabella | highest midline vertex; posterior / anterior midline relative to eye height and the eye–vertex distance |
| chin | lowest protruding anterior midline vertex below the mouth |
| tragus, outer canthus, infraorbital | ear front at 0.11 × eye–vertex below eye height; next to the eye centre; 1.8 cm below the eye centre |
| mastoid, gonion | offsets from the tragus (behind/below; 5 cm below, in front of the ear lobe) |
| acromion, coracoid | vertex near the shoulder joint maximising `z + 0.5·|x|`; anterior 3.5 cm below it, at 0.78 × acromion x |
| scapula superior angle / spine root / inferior angle | posterior-most at 0.824 / 0.808 / 0.745 of stature, 0.42 / 0.38 / 0.45 × acromion x |
| costal margin | anterior at 0.668 of stature, midclavicular line (0.5 × acromion x) |
| ASIS, PSIS | anterior at 0.562 of stature, x = 0.75 × greater trochanter (inter-ASIS ≈ 0.75 × bitrochanteric); posterior at 0.556, 4.5 cm from the midline |
| iliac crest, greater trochanter | most lateral trunk vertex at 0.598 of stature / at hip-joint height |
| humeral epicondyles, olecranon | extremes along the elbow flexion axis (cross product of upper arm and forearm); posterior-most at the elbow |
| radial / ulnar styloid | extremes towards the thumb / little finger, 0.5–3 cm proximal to the wrist joint |
| patella, femoral epicondyles, fibular head | anterior-most just above the knee joint; lateral / medial extremes at the knee; lateral 2.5 cm below it |
| malleoli, heel | lateral / medial extremes at the ankle joint; posterior-most foot vertex below 5 cm |

Calibration only fills anchors that are `null`; `--overwrite` replaces all. The 24 anchors that
existed before the 2026-10-26 extension kept their vertex IDs (the shared rules reproduce 18 of them
exactly and the rest within 2 cm, except the iliac crest at 4 cm). ASIS was recalibrated: the old
inter-ASIS distance was 15 cm, against about 24 cm in adults.

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
or walks. The `procedural` bone meshes (vertebrae, ribs, sternum) use the same parents.

## 6.5 QA image

With `preview.landmark_overlay: true` (`export.yaml`, off by default), each human gets `<id>_landmarks.png`: front and side views
with **red** = internal vertebrae, **yellow** = surface vertebrae, **cyan** = anchors. Check that:
red lies inside the body in front of yellow, both run C1 → S5 top to bottom, and the cyan points sit
on the ears, shoulders, pelvis and heels.

## 6.6 Accuracy and limits

* Landmarks are **anthropometric estimates from the body surface**, not CT/MRI-derived anatomy.
  Vertebral levels follow population-average segment proportions between four pinned levels.
* Pinned levels inherit the anchor rules above; expect ±1 vertebral level of uncertainty in the
  mid-thoracic region and ±1–2 cm in internal depth.
* The rest pose is MPFB's A-pose. Kyphosis, lordosis and scoliosis are sampled per human for the
  vertebral bodies only (§6.8, `spine_shape`); the skin and the surface points are not reshaped.
* For higher fidelity, replace the rules with vertex IDs selected by a radiologist on the neutral
  mesh (§6.2), or adjust `segment_ratios` / `internal_depth`.

## 6.7 Adding a landmark

1. `anchors.my_point: <vertex id>`
2. `parent_bones.my_point: spine04` (or `my_point_{side}: "clavicle.{side}"` with `_L`/`_R` anchors)
3. optional `heights_from_landmarks.my_point: my_point_height_cm`

The new point `LM_my_point` appears in the metadata and in the overlay, and in the USD with the
`procedural` / `none` layers.

## 6.8 Derived joints, spinal shape and exam posing (2026-10-26)

For results on MPFB and MHR side by side, see [13 MPFB vs MHR](13_mpfb_vs_mhr.md).

Built from the landmarks by `sdg_humans/anatomy_rules.py` (identical in the MHR pipeline), so the
skeleton carries **175 `LM_` + 36 `AN_` joints** in total:

| Group | Joints | Rule |
|---|---|---|
| Anatomical joint centres | `LM_{hip,shoulder,elbow,wrist,knee,ankle}_centre_L/R` | hip: Harrington 2007 from ASIS/PSIS; shoulder: Rab 2002 (0.17 × biacromial below the acromion); others: midpoints of epicondyles / styloids / malleoli (ISB) |
| Rib cage | `AN_rib01…12_L/R` (costovertebral, X along the rib), `LM_rib01…12_end_L/R` | rib drop / end angle as in `anatomy.yaml`, chest width 0.8 × acromion x |
| Sternum | `AN_manubrium`, `AN_sternum_body`, `AN_xiphoid_process` | surface landmark + soft tissue (max(1 cm, 6 % of chest depth)) |
| Ankle axes | `AN_talocrural_L/R` (Z = malleolar axis), `AN_subtalar_L/R` (X = Inman axis, 42° up, 23° medial) | malleoli, heel, metatarsal heads |
| Internal points | `LM_hyoid`, `LM_carpus_L/R`, `LM_calcaneus_L/R`, `LM_patella_internal_L/R` | offsets from C3 / wrist / heel / patella |
| Foot anchors | `LM_metatarsal_head_1_L/R`, `LM_metatarsal_head_5_L/R` | medial / lateral forefoot at the toe base |

**Spinal shape** (`landmarks.yaml → spine_shape`): per human, kyphosis T4–T12, lordosis L1–S1 and
(with an age-dependent probability) a scoliosis are sampled; the vertebral bodies `LM_C1…S5` are
reshaped to these Cobb angles (sacrum fixed, C1 kept in place), and scoliotic vertebrae get an axial
rotation. Before / target / after values are in `<id>.json → spine_shape`. The skin is not changed.

**Exam posing** (`scripts/pose_exams.py`, `sdg_humans/pose_rules.py`, rig roles in `configs/poses.yaml`):

```bash
.venv/bin/python scripts/pose_exams.py <run>/humans/H0001/H0001.usd     # -> H0001_exam_poses.usda + .json
```

Posing drives MPFB joint names (`configs/poses.yaml`), so it needs a human built with
`skeleton.layer: procedural` or `none`; `zanatomy` humans have the anatomical rig (14).

* poses `neutral`, `chest_pa` (hands on hips, shoulders forward, full inspiration), `chest_lateral`
  (arms overhead, full inspiration), `spine_ap`, `spine_lateral` (arms forward), `trunk_flexion_30`,
  `invalid_test`: one time sample each in a UsdSkelAnimation that references the human;
* arms by 2-bone IK, with the humerus twisted so that the epicondyle axis is the elbow hinge;
* coupled motion of the annotation joints: vertebrae and ribs follow the axial chain smoothly (by
  height); the scapula rotates upwards by ⅓ of the humeral elevation above 30°; the patella follows
  70 % of knee flexion; forearm / upper-arm twist is shared over the split bones; screw-home tibial
  rotation; breathing elevates the ribs (4–8°) and moves the sternum;
* `pelvis_L/R` and the index / middle metacarpals are locked (rigid in a real body);
* every pose is checked against a normal adult range-of-motion table (`pose_rules.ROM`, can be
  overridden in `poses.yaml → rom`); violations are listed in the JSON report.
