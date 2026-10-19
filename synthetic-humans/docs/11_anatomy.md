# 11. Anatomical skeleton (bone meshes)

Each human gets a **schematic anatomical skeleton**: about 80 bone meshes inside the body,
generated per human from that human's rig joints, spine landmarks and body surface. Each bone
mesh is skinned to its rig bone, so the skeleton moves with the body in Isaac Sim (walking,
positioning) and can be rendered, segmented or used for X-ray-like simulation.

> These bones are **procedural approximations** (tubes, ellipsoids and plates placed with
> anatomical rules), not imaging-derived anatomy. They give correct proportions, positions and
> topology (which bone is where and how it moves), not detailed bone shape.

## 11.1 Bones generated

| Group (`parts`) | Meshes (`bone_<name>`) | Built from | Skinned to |
|---|---|---|---|
| `skull` | `skull` (cranium + facial skeleton), `mandible` | vertex, nasion, inion, tragus L/R, chin landmarks | head, jaw |
| `vertebrae` | `vertebra_C1 … vertebra_L5` (body + spinous + transverse processes), `vertebra_S1 … S5` (sacral segments), `coccyx` | internal + surface spine landmarks | the landmark's parent bone (neck01–03, spine05–01, root) |
| `ribs` | `rib_L_01 … rib_L_12`, `rib_R_01 … rib_R_12` | T1–T12 landmarks + rays to the inner chest wall | spine05 / spine04 / spine03 |
| `sternum` | `sternum` | jugular notch → xiphoid landmarks | spine04 |
| `shoulder_girdle` | `clavicle_L/R`, `scapula_L/R` | jugular notch, acromion, T2/T7 levels, back surface | clavicle.L/R, shoulder01.L/R |
| `pelvis` | `ilium_L/R`, `ischiopubic_L/R` | S1, iliac crest, ASIS landmarks, hip joints | pelvis.L/R |
| `limbs` | `humerus`, `radius`, `ulna`, `femur`, `patella`, `tibia`, `fibula` (each `_L/_R`) | rig joint positions; trochanter landmark | upperarm01/02, lowerarm01/02, upperleg01/02, lowerleg01/02 (blended across twist bones) |
| `hands_feet` | `hand_L/R` (carpals, metacarpals, phalanges), `foot_L/R` (tarsals, calcaneus, metatarsals, phalanges) | finger / toe / wrist / foot bones, heel landmark | wrist, metacarpal*, finger*, foot, toe* |

## 11.2 How it is built (`sdg_humans/blender/anatomy/`)

| Module | Job |
|---|---|
| `prims.py` | mesh accumulator with per-vertex skin weights; tubes (elliptical, tapered), ellipsoids, surface patches; twist-bone weight blending |
| `axial.py` | skull, vertebrae, coccyx, ribs, sternum |
| `appendicular.py` | clavicles, scapulae, hip bones, long bones, patellae, hands, feet |
| `build.py` | context (landmarks, rig joints, ray-cast helpers), one object per bone, skeleton preview |

Rules (sizes scale with stature / 170 cm):

* **Vertebrae** sit on the internal spine landmarks (doc 06). The body is a short elliptical
  cylinder along the local spine axis (radius C 0.9 / T 1.3 / L 2.0 cm). The spinous process runs
  to just under the surface landmark, plus two transverse processes. Sacral segments are wide flat
  ellipsoids that narrow from S1 to S5.
* **Ribs:** for rib *i*, rays are cast from inside the chest at the T*i* level towards the chest
  wall, sweeping from next to the spine round to `rib_end_angle_deg[i]` from the front midline. The
  front end drops `rib_anterior_drop_cm[i]` below the vertebra. Each rib point lies
  `max(soft_tissue_cm, soft_tissue_fraction × distance)` inside the skin, so heavier bodies get a
  thicker chest wall. Ribs 1–7 reach the sternum, 8–10 stop short and 11–12 float.
* **Scapulae** are plates between the superior angle (T2 level), the inferior angle (T7 level) and
  the glenoid / acromion, projected onto the inside of the back surface. They get thickness from a
  Solidify modifier.
* **Pelvis:** each ilium is a plate between the PSIS (beside S1), the iliac crest, the ASIS and the
  acetabulum (femoral head), plus a pubis–ischium ring.
* **Long bones** follow the rig joints (shoulder → elbow → wrist, hip → knee → ankle), with knobs
  for the joints. Weights hand over between the MPFB twist bones (upperarm01 → upperarm02, …) so
  the bones twist with the limb.

## 11.3 Configuration (`configs/anatomy.yaml`)

| Key | Default | Meaning |
|---|---|---|
| `enabled` | true | build the skeleton at all |
| `parts` | all 8 groups | groups to build (`skull, vertebrae, ribs, sternum, shoulder_girdle, pelvis, limbs, hands_feet`) |
| `color_rgb` | `#e3d8c3` | bone material colour (UsdPreviewSurface) |
| `soft_tissue_cm`, `soft_tissue_fraction` | 1.2, 0.08 | depth of ribs / sternum / scapulae below the skin |
| `rib_anterior_drop_cm` | 12 values | front-end drop per rib |
| `rib_end_angle_deg` | 12 values | where each rib ends (angle from the front midline) |
| `min_depth_below_skin_cm` | 0.4 | every bone vertex is pulled at least this far inside the skin (no bone shows through on unusual faces / bodies) |
| `preview` | true | write `<id>_skeleton.png` (bones only, front + side) |

## 11.4 In the USD and metadata

Bone meshes are skinned meshes under the human's SkelRoot, next to the body:

```
/H0001/H0001_rig/bone_femur_L/bone_femur_L      Mesh (SkelBindingAPI → upperleg01.L / upperleg02.L)
/H0001/H0001_rig/bone_rib_L_05/bone_rib_L_05    Mesh (→ spine04)
/H0001/_materials/H0001_bone                    UsdPreviewSurface
```

`H0001.json → anatomy.bone_meshes` lists every bone: `name`, `object`, `rig_bone`, `part`,
`vertices` and `usd_prim`. In Isaac Sim you can, for example:

* hide the body and clothes to visualise the skeleton,
* assign semantic labels per `bone_*` prim for segmentation (Replicator),
* give the bone prims a different material for X-ray-style renders.
