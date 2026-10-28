# 14. Skeletal layer

The skeleton is a **separate, swappable layer**. The body, skin, clothing and hair build does not depend on it, so the
skeleton can be changed later without touching the rest of the pipeline.

```
configs/skeleton.yaml -> layer: zanatomy | procedural | none
sdg_humans/skeleton/
├── __init__.py        registry (LAYERS), SkeletonLayer base, LayerContext, LayerResult
├── procedural.py      'procedural' (bones built in Blender, MPFB rig) and 'none'
└── zanatomy/          'zanatomy': Z-Anatomy skeleton fitted into the finished body
    ├── __init__.py    ZAnatomyLayer: checks -> fit -> USD rewrite -> metadata
    ├── reference.py   the reference package (assets/zanatomy)
    ├── fit.py         torch fit of the skeleton into the body
    ├── weights.py     MakeHuman -> anatomical skin weights
    └── usd_rig.py     rig swap, re-skinning and bone meshes in the USD (usd-core)
```

| Layer | Bones | Rig in the USD | Where it runs |
|---|---|---|---|
| `zanatomy` (default) | 158 Z-Anatomy meshes (156 bones + teeth), `bone_*` / `teeth_*`, purpose `guide` | **anatomical**: `SkelOrigin` + 156 Z-Anatomy joints only | host, after `usd_post`, before validation |
| `procedural` | ~80 schematic meshes (docs/11) | MPFB default rig + `LM_*` / `AN_*` landmark joints | Blender build |
| `none` | – | MPFB default rig + landmark joints | – |

## Where the layer runs in the pipeline

```
Blender build:  body … clothing → floor → landmarks → measure
                → [procedural: anatomy bones] | [zanatomy: save the closed body → work/<id>/skeleton_body.npz]
                → finalize → preview → USD export → metadata
host:           usd_post (clothing holes, SkelOrigin root) → skeletal layer apply() → validate
```

A layer declares three things:
- `builds_in_blender`: the Blender build makes the bones.
- `needs_body_dump`: Blender saves the full closed body for `apply()`. The exported body has holes under clothes
  and may lack vertices under shoes.
- `rig_replaced`: animation that drives MPFB joint names (`export.animation`) is skipped with a warning.

`apply(ctx) -> LayerResult` returns the `anatomy` and `skeleton` metadata blocks, the landmark joint path changes and
any warnings. The orchestrator merges them into `<id>.json` (also `skeleton_layer`, `versions.skeleton_layer`).

**Adding a skeleton:** write a module with a `SkeletonLayer` subclass, register it in `LAYERS`, and add its settings
block under its name in `skeleton.yaml`. Nothing else changes.

## The `zanatomy` layer

The method comes from the research spike `../zanatomy-humans/spike` (REPORT.md, step S9). There it was the only
approach that keeps the human realistic.

1. **The human is not changed.** The layer works in skeleton space. It first checks that the saved closed body
   matches the exported body (≤ `body_match_tolerance_mm`).
2. **Fit** (`fit.py`, about 15–30 s per human on CPU). Every anatomical bone gets a rotation, a length scale
   (0.78–1.28 of the stature scale) and a breadth/depth scale (0.67–1.49). Children attach at the parent's scaled
   point, so the skeleton stays connected and every bone keeps its real shape. Losses:
   - **joint prior:** each joint where its ring of reference-skin vertices puts it (MakeHuman topology gives the
     vertex correspondence);
   - **bony landmarks in reverse:** 59 landmarks, each placed at its skin point minus a soft-tissue depth, with the
     depths scaled by BMI;
   - **containment:** bones inside the skin; faded in once the skeleton is placed;
   - **symmetry** and **smoothness** (vertebra and rib chains).
3. **USD rewrite** (`usd_rig.py`):
   - the Skeleton becomes `SkelOrigin` + the 156 Z-Anatomy joints;
   - every skinned mesh is re-weighted. Limb, girdle and head bones map 1:1. The MakeHuman spine/neck weights are
     split over the 24 vertebrae by projecting onto the fitted vertebra chain. Top 4, normalised;
   - the Z-Anatomy meshes are added under `<SkelRoot>/ZAnatomy`, rigid to their bone, with one bone material;
   - the CC BY-SA attribution goes in `customLayerData`.
4. **Metadata** (`<id>.json`):
   - `anatomy = {source: zanatomy, reference_version, bone_meshes[], fit{…}, points_m{…}}`. `points_m` holds the
     fitted joint centres and bony landmarks (world, metres) of all 272 Z-Anatomy points;
   - `skeleton.rig = zanatomy_anatomical`.

   The MPFB surface landmarks stay in `landmarks` as data, with `usd_joint: null`.

Typical result (2026-10-27 runs): landmark residual median 9–10 mm (p90 ~25 mm), and ~1–1.5 % of bone samples
outside the skin. The bones are `guide`, so they never show in RGB renders. Known limits:
- the sternum sits 2–3 cm out in very slim men (Z-Anatomy is one man with a deep chest);
- the scapula is a little out in arms-up poses (skin weights);
- the pelvis keeps its male shape in women.

See the spike report.

### Consequences of the anatomical rig
- `../sdg` retargeting (`configs/retarget_mpfb.yaml`), `scripts/pose_exams.py`, `isaac/motion.py` and
  `export.animation` drive **MPFB joint names**, so they do not apply to `zanatomy` humans. A retarget map for the
  anatomical names belongs to the animation scope. Use `layer: procedural` or `none` when MPFB-rig animation is
  needed.
- With `keep_landmark_joints: true`, the `LM_*` / `AN_*` joints are kept, re-parented under the anatomical bones (world
  position unchanged). The default is a Z-Anatomy-only rig.

### Setup
```bash
.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_zanatomy_reference.py      # -> assets/zanatomy (reference.npz, maps.json, manifest.json)
```
The reference package is built from the spike outputs (`output/zanatomy-humans/spike`). If those are missing, the
script reruns the spike (needs Blender + MPFB + the Anny venv). Preflight checks torch, scipy and the package's
sha256s.

### Licence
The bone meshes are **CC BY-SA 4.0** (Z-Anatomy, derived from BodyParts3D). Exported USDs carry the attribution and
must be shared alike. `assets/zanatomy/` is gitignored.