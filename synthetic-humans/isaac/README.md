# Animating the humans in Isaac Sim

Three small scripts (only `pxr` needed: usd-core, or the Python that ships with Isaac Sim):

| File | Where it runs | What it does |
|---|---|---|
| `motion.py` | anywhere | procedural motion definition (no pxr) |
| `animate_human.py` | terminal / Isaac Python | writes `<id>_anim.usda`: the human referenced + `UsdSkelAnimation` + root motion |
| `play_in_isaac.py` | Isaac Sim → Window → Script Editor | loads one or more `*_anim.usda`, plays the timeline, prints landmark positions |

The pipeline writes `<id>_anim.usda` automatically next to every `<id>.usd`
(`export.animation.enabled: true`), so usually you only need step 2 below.

## 1. Create an animated scene (if not done by the pipeline)

```bash
python isaac/animate_human.py <run>/humans/H0001/H0001.usd
python isaac/animate_human.py H0001.usd --out my_scene.usda --walk-distance 4 --walk-speed 1.0 --jump-height 0.3 --fps 30
```

## 2. Play it in Isaac Sim

* Simplest: *File → Open* `H0001_anim.usda`, then press **Play**.
* Several humans: edit `HUMANS` in `play_in_isaac.py`, paste it into the Script Editor and run it.
  Each human is referenced under `/World/Patients/Pxxx`, 1.5 m apart, and the timeline loops.

## Motion (default 16 s at 30 fps)

| Segment | Duration | What happens |
|---|---|---|
| idle | 2.0 s | standing, arms down, breathing sway |
| walk | ~2.6 s | walks 3 m forward (−Y) with leg / arm swing and torso twist |
| idle | 1.5 s | standing |
| jump | 1.9 s | crouch → push → airborne (0.22 m) → landing → recover |
| idle | 1.0 s | standing |
| turn | 1.2 s | turns 180° with small steps |
| walk | ~2.6 s | walks back to the start |
| turn | 1.2 s | turns back to the original direction |
| idle | 2.0 s | standing at the original place |

How it works:

* Rotations are defined in skeleton space (hip / knee / ankle flexion about X, arms lowered from
  MPFB's A-pose about Y) and converted to each joint's local frame from the rest pose.
* Forward kinematics runs every frame, and the human is moved vertically so the lowest foot / toe
  joint stays on the floor. Crouching therefore lowers the body, and the jump's lift is added on top.
* Walking and turning drive the referenced prim's `translate` and `rotateZ` (root motion). The
  skeleton animation itself is in place.
* Every joint not animated keeps its rest transform. The `LM_*` landmark joints and the bone meshes
  follow automatically, and so do the clothes (skinned to the same skeleton; the gown hem uses
  blended weights so it sways between the legs).

## Reading landmarks during the animation

`play_in_isaac.py` prints selected `LM_*` joint world positions every `PRINT_EVERY` frames. For your
own pipeline use `sdg_humans/isaac_landmarks.py`:

```python
from sdg_humans.isaac_landmarks import LandmarkReader
reader = LandmarkReader(stage, "/World/Patients/P000/H0001/H0001_rig/H0001_rig")
positions = reader.world_positions(Usd.TimeCode(frame))     # {"T7": (x, y, z), ...}
```

## Limits

* Procedural motion: plausible, but not motion capture. There is some foot sliding during walk and
  turn, and no inverse kinematics.
* Clothing deforms by skinning only (no cloth simulation). For real cloth dynamics, Isaac Sim's
  PhysX deformable / particle cloth can be applied to the gown mesh. That is not set up here.
* To use your own clips, retarget BVH / FBX motion onto the MPFB default rig in Blender, or replace
  `motion.pose_at()`.
