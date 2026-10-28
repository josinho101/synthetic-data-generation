# 7. USD & Isaac Sim

## 7.1 Export settings (`blender/usd_export.py`)

Before export:

1. **Bake the body:** all MPFB shape keys (macros + face targets) are merged into the mesh
   (`TargetService.bake_targets`). The helper-mask modifier is removed and helper / joint-cube
   geometry is deleted (13 380 body vertices remain).
2. **Apply non-armature modifiers** on every mesh (gown smoothing, inflation, solidify) in the
   rest pose.
3. **Clean weights:** non-bone vertex groups are deleted, each vertex keeps ≤ 4 bone influences,
   and the weights are normalised.

`bpy.ops.wm.usd_export` options:

| Option | Value | Why |
|---|---|---|
| `selected_objects_only` | armature + its meshes | nothing else (lights, cameras) |
| `export_armatures` | true | UsdSkel `SkelRoot` + `Skeleton` + skinning |
| `only_deform_bones` | **false** | keeps the non-deforming `LM_*` / `AN_*` landmark joints |
| `export_shapekeys` | false | already baked |
| `export_animation` | false | rest pose only; animation happens in Isaac Sim |
| `generate_preview_surface` | true | `UsdPreviewSurface` materials (Isaac Sim / RTX render them) |
| `export_textures_mode` | KEEP + `relative_paths` | textures referenced as `textures/<file>.png` |
| `convert_scene_units` / `meters_per_unit` | METERS / 1.0 | Isaac Sim default stage units |
| `export_global_up_selection` | Z | Isaac Sim is Z-up |
| `root_prim_path` | `/<id>` | default prim = the human |
| `convert_world_material`, `export_lights`, `export_cameras` | false | no preview environment in the asset |

## 7.2 Prim hierarchy

Default (`skeleton.layer: zanatomy`), e.g. a man in a full outfit:

```
/H0001                                   Xform (defaultPrim)
├── H0001_rig                            SkelRoot
│   ├── H0001_rig                        Skeleton (SkelOrigin + 156 Z-Anatomy joints = 157)
│   ├── H0001/base                       Mesh (body, SkelBindingAPI, 4 influences, clothing holeIndices)
│   ├── H0001_male_casualsuit03/male_casualsuit03   Mesh (garment, skinned)
│   ├── H0001_mindfront_shoes_…/shoes_…  Mesh (shoes)
│   ├── H0001_short01/short01, H0001_eyebrow002/…, H0001_eyelashes01/…   hair, brows, lashes
│   ├── H0001_eye_L/H0001_eye_L          Mesh + GeomSubsets sclera/iris/pupil
│   ├── H0001_eye_R/H0001_eye_R
│   └── ZAnatomy                         Xform, purpose guide (doc 14)
│       ├── bone_femur_L … teeth_*       158 rigid bone / teeth meshes
│       └── Looks/ZAnatomyBone           bone material
└── _materials/                          Scope
    ├── H0001_skin                       UsdPreviewSurface ← textures/H0001_skin.png
    ├── H0001_full_body, H0001_feet, H0001_hair, …   garments, hair (baked textures)
    └── H0001_sclera / _iris / _pupil
```

The CC BY-SA attribution of the bones is in the layer's `customLayerData` (`zanatomy:*`). Joint paths start with
`SkelOrigin/pelvis/…`, e.g. `SkelOrigin/pelvis/vertebra_L5/…/vertebra_T7`.

With `layer: procedural` / `none` the skeleton is the MPFB default rig plus the landmark joints: `SkelOrigin` +
163 rig joints + 175 `LM_*` + 36 `AN_*` = 375 joints, e.g.
`SkelOrigin/root/spine05/spine04/spine03/spine02/spine01/neck01/neck02/neck03/LM_C7`. Joint paths follow the Blender
bone hierarchy with `.` replaced by `_`. `procedural` puts its ~80 skinned bone meshes directly under the SkelRoot
(`bone_skull/bone_skull`, …, doc 11) with the material `_materials/H0001_bone`.

The exact path of each landmark joint (or `null`) is in `H0001.json → landmarks.<name>.usd_joint`, and the skeleton
prim is in `skeleton.usd_skeleton_prim`.

## 7.2a Post-export fixes (`usd_post`)

Applied on the host after the Blender export, before validation, and recorded in `<id>.json → usd_post`:

| Fix | What | Why |
|---|---|---|
| clothing holes | `holeIndices` on `H0001/base` = body faces whose vertices are all covered by one of the human's garments (a ray along the vertex normal hits the garment within `clothing_reach_cm`) | body and garments are skinned with different weights; in poses (arms up, hands on hips) the skin pushed through close-fitting cloth. Skin at hems, collars and sleeve openings stays |
| anatomy purpose | `purpose = guide` on every `bone_*` prim (`procedural` layer; the `zanatomy` layer sets its own `bone_purpose`) | the rigid bone meshes poke through the skin in strong poses; they stay in the file for later use (switch on guides in the viewport, or set `anatomy_purpose: default`) |
| root joint | `SkelOrigin` (identity) above `root`; joint paths, rest/bind transforms, per-joint primvars and the meshes' `skel:joints` updated; `landmarks.*.usd_joint` in the JSON too | retargeters need the hips below a root joint at the origin |

## 7.3 Validation (`scripts/validate_usd.py`, also run after every build, after the skeletal layer)

| Check | Failure level |
|---|---|
| stage opens; `upAxis = Z`; `metersPerUnit = 1.0`; defaultPrim set | error |
| exactly one `SkelRoot` and one `Skeleton` | error |
| every mesh has `SkelBindingAPI` + `jointIndices`; element size ≤ `max_bone_influences` | error |
| every texture referenced by a shader exists | error |
| every non-null `usd_joint` listed in the metadata exists in the skeleton | error |
| skinned head height within 1.5 cm of stature + `footwear_lift_cm`; lowest point (incl. footwear) within 1 cm of z = 0 | warning |
| rest pose = bind pose (identity skinning transforms) | warning |
| mesh without a bound material (and without subsets) | warning |

## 7.4 Importing into Isaac Sim

1. *File → Open* `H0001.usd` (to inspect), or **reference** it into your room stage:
   *Create → Reference* / drag the file from the Content browser onto the stage.
2. Keep the folder intact: the textures are referenced relative to the USD file.
3. Units: the asset is in meters and Z-up, like the Isaac Sim default stage. No scaling is needed.
4. Feet stand at z = 0 and the human faces −Y. Rotate the referenced prim to face the detector.
5. For several humans in one stage, reference each one under its own Xform, e.g.
   `/World/Patients/H0001`.

Script version:

```python
from pxr import Usd, UsdGeom, Gf
import omni.usd

stage = omni.usd.get_context().get_stage()
patient = stage.DefinePrim("/World/Patients/H0001", "Xform")
patient.GetReferences().AddReference("/path/to/run-…/humans/H0001/H0001.usd")
UsdGeom.XformCommonAPI(patient).SetTranslate(Gf.Vec3d(1.0, 2.0, 0.0))
```

## 7.5 Animating

The skeleton is a standard UsdSkel skeleton. With the default `zanatomy` layer it is the **anatomical
rig** (`SkelOrigin` → pelvis → sacrum / femurs, and vertebrae L5…C1 → skull; ribs hang on their
vertebrae; T4 → sternum → clavicles → scapulae → humerus → radius / ulna …); MPFB-name tools (`isaac/`, `pose_exams.py`, `../sdg` retargeting) do not apply,
and a retarget map for the anatomical names is still to be written (doc 14).

With `procedural` / `none` it is the MPFB *default* rig (root → pelvis / spine05–01 → neck01–03 →
head, clavicles, arms, legs, fingers). Animations can be authored as `SkelAnimation` (retargeted from
MPFB/BVH clips in Blender, or with Isaac Sim's animation retargeting extension). The `LM_*` / `AN_*`
joints carry no weights, so they never deform the mesh and simply follow their parent bones.

## 7.6 Reading landmarks in Isaac Sim

This needs landmark joints in the USD (`procedural` / `none` layer, or `zanatomy` with
`keep_landmark_joints: true`). For default `zanatomy` humans the landmarks are rest-pose data in
`H0001.json → landmarks` and `anatomy.points_m`.

```python
from pxr import Usd, UsdGeom, UsdSkel
import omni.usd

stage = omni.usd.get_context().get_stage()
skel_prim = stage.GetPrimAtPath("/World/Patients/H0001/H0001_rig/H0001_rig")   # referenced skeleton.usd_skeleton_prim
skel_cache = UsdSkel.Cache()
skel_query = skel_cache.GetSkelQuery(UsdSkel.Skeleton(skel_prim))
joints = list(skel_query.GetJointOrder())

def landmarks_world(time=Usd.TimeCode.Default()):
    """{landmark_name: (x, y, z) in stage meters} for the current frame."""
    local = skel_query.ComputeJointSkelTransforms(time)                       # skeleton space
    to_world = UsdGeom.Xformable(skel_prim).ComputeLocalToWorldTransform(time)
    out = {}
    for path, xf in zip(joints, local):
        name = path.split("/")[-1]
        if name.startswith("LM_"):
            out[name[3:]] = tuple((xf * to_world).ExtractTranslation())
    return out

print(landmarks_world()["T7"], landmarks_world()["tragus_L"])
```

The same logic is packaged as `sdg_humans/isaac_landmarks.py` (depends only on `pxr`; copy it
into your Isaac Sim extension or add `mpfb-humans` to `sys.path`):

```python
from sdg_humans.isaac_landmarks import LandmarkReader
reader = LandmarkReader(stage, "/World/Patients/H0001/H0001_rig/H0001_rig")
positions = reader.world_positions(timecode)       # {"T7": (x, y, z), "tragus_L": (...), ...}
```

This was verified against exported files: positions read from the USD skeleton match
`H0001.json → landmarks.*.rest_position_m` to 0.1 mm in the rest pose.

Use `UsdSkel.Cache` once per stage and call `landmarks_world(time)` each simulation step (or from a
Replicator writer) to write per-frame annotations together with the static metadata from
`H0001.json` (height, ear height, …).
