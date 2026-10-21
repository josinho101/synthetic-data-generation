# 1. Overview & architecture

## 1.1 What the pipeline does

`sdg` is the third pipeline of the X-ray room digital twin. It takes:

* synthetic patients from [synthetic-humans](../../synthetic-humans/README.md): rigged MPFB humans as UsdSkel USD, with
  landmark metadata;
* X-ray rooms from [room](../../room/README.md): room USD with markers, patient route, equipment and D455 cameras.

It plays an **X-ray exam visit live in Isaac Sim**, one human in one room at a time:

| # | Phase | What the patient does |
|---|---|---|
| 1 | arrival | is loaded **outside the room**, 1.5 m in front of the entrance door, and stands idle |
| 2 | check-in | walks through the entrance into the **check-in room** |
| 3 | entrance marker | walks through the connecting door into the **X-ray room** and stands idle on the **entrance marker** |
| 4 | detector marker | walks to the **detector marker**, turns to face the detector and stands idle |
| 5 | projections | for each projection: turns, raises the arms into the pose, the **FOV light** is on for 1 s and then off, and the arms go down |
| 6 | exit | walks back to the **door (entrance) marker**, then leaves through the check-in room to the start point outside |

Default projections (chest), all configurable:

| Projection | Facing | Arms |
|---|---|---|
| PA | faces the detector (back to the tube) | hands on hips |
| LLAT | turns 90° **right** from facing the detector, so the left side is on the detector | hands on head |
| RLAT | turns 90° **left**, so the right side is on the detector | hands on head |

Spine T/L PA, LLAT and RLAT come later and only need configuration ([09](09_extending.md)).

The record of a visit is a **time-stamped `timeline.txt`** in the human's SD folder ([06](06_output_schema.md)).
This stage captures no images or frames.

## 1.2 Architecture: two processes

```
 host Python (.venv)                                  Isaac Sim 6.2 (python.sh + SimulationApp)
 ───────────────────                                  ──────────────────────────────────────────
 scripts/run_pipeline.py                              isaac/run_exam.py
   load configs/*.yaml (+ --set)                        per visit:
   resolve humans / rooms runs   ──► job.json ──►         new in-memory stage
   plan each visit (steps)          (temp file)           room + motion library + patient agent
   human arm targets, T7 height                           NavMesh bake + route check
   create SD folders, sd_info.json                        execute steps via the behavior agent API
   start Isaac, stream console   ◄── "[xray] ..." ──      write timeline.txt, update sd_info.json
   final status per SD, exit code                       close Isaac
```

* **Host side** (`sdg_xray/`): pure Python plus `pyyaml`. It is testable without Isaac. It decides *what* happens:
  inputs, route, steps, timings and hand targets.
* **Isaac side** (`isaac/run_exam.py`): runs inside Isaac Sim's own Python. It decides *how* the motion looks, using
  Isaac's behavior system (`omni.anim.behavior`): NVIDIA's human motion library retargeted onto the MPFB rig,
  NavMesh path finding and hand IK.
* Both sides exchange a single job JSON (temporary, deleted after the run) and the console lines prefixed `[xray]`.
* **Nothing is saved as USD.** The stage is built in memory from references to the room and human USDs, and the
  source files are never modified.

## 1.3 Code map

| File | Role |
|---|---|
| `scripts/run_pipeline.py` | CLI: arguments → config overrides → `run_pipeline` |
| `sdg_xray/config.py` | loads `configs/*.yaml`, `--set` overrides, validation |
| `sdg_xray/sources.py` | finds the humans / rooms run (latest or configured) and selects ids |
| `sdg_xray/visit.py` | room anchors → visit plan (steps); T7 (detector) height |
| `sdg_xray/pose_clips.py` | arm poses → custom-action clips on the motion library skeleton (two-bone IK, blend in / hold / blend out) |
| `sdg_xray/pipeline.py` | orchestration: jobs, SD numbering, job file, launch, final status |
| `sdg_xray/launcher.py` | starts `python.sh run_exam.py`, streams and filters its console, timeouts, exit code |
| `sdg_xray/sd.py` | SD numbering, `sd_info.json` writing, `Timeline` writer (also used inside Isaac) |
| `sdg_xray/paths.py` | project paths and default input / output roots |
| `isaac/run_exam.py` | inside Isaac: stage build, retarget, NavMesh, FOV light, behavior agent, step execution |
| `../room/isaac/compose_scene.py` | `compose_into()`: room reference + detector / tube at the patient's T7 height (shared with the room pipeline) |

## 1.4 Coordinate frames

* **Stage frame** (everything in this pipeline): meters, Z up. The room is centred at the origin with the entrance
  door facing −Y (room pipeline `export.placement`). Positions come from `<room>.json → anchors.stage.*`.
* **Body frame** of a human (landmarks, pose checks): +X = the patient's left, −Y = front, +Z = up, feet at z = 0.
  This is the MPFB skeleton space. At run time a body-frame vector `v` becomes
  `left·v.x + front·(−v.y) + up·v.z`, where `front` is the agent's current facing direction.
* **Motion library frame** (arm poses in `poses.yaml`): NVIDIA's "Human" rig, cm, +X = left, +Y = up, +Z = front.
* **Facing** directions are unit vectors in the stage XY plane. "Facing the detector" is `−anchors.stage.detector_normal`
  (the detector normal points from the detector towards the patient). *Left* turns this vector +90° (counter-clockwise
  seen from above), *right* turns it −90°.

Check of the lateral conventions: after a left turn (RLAT), the patient's right side, which is the facing vector
turned −90°, points at the detector. A unit test verifies this.

## 1.5 What the pipeline reads from the other pipelines

| Source | Field | Used for |
|---|---|---|
| `<room>.json` | `anchors.stage.patient_route` (entrance, check_in, connecting_door, entrance_stand, patient_stand) | walk waypoints |
| | `anchors.stage.entrance_door`, `entrance.out_normal`, `placement.yaw_deg` | start point outside, facing the door |
| | `anchors.stage.entrance_yaw_deg` | facing on the entrance marker (into the room) |
| | `anchors.stage.detector_normal` | facing the detector, and the left / right turns |
| `<room>.usd` | `/Room/Markers/PatientStand`, `Equipment/WallStand/Carriage`, `TubeStand/.../TubeHead/Collimator/LightWindow` | stage build, detector height, FOV light |
| room `results.json`, `manifest.json` | status per id | input selection |
| `<human>.json` | `landmarks.T7.rest_position_m` | detector / tube height |
| | `measurements_cm.jugular_notch_height_cm` / `xiphoid_height_cm` | T7 fallback |
| | `body.height_cm` | logs, `sd_info.json` |
| `<human>.usd` | UsdSkel skeleton (MPFB default rig, 247 joints); `bone_*` anatomical skeleton meshes (hidden) | behavior agent |
| human `results.json` | status per id | input selection |
