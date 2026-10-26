# sdg

Third pipeline of the X-ray room digital twin. It takes the synthetic patients from
[mpfb-humans](../mpfb-humans/README.md) and the X-ray rooms from [room](../room/README.md), and animates
**X-ray exams live in Isaac Sim**. One human visits one room at a time:

1. The patient is loaded **outside the room**, in front of the entrance.
2. They walk through the entrance into the **check-in room**.
3. They walk through the connecting door into the **X-ray room** and stand idle on the **entrance marker**.
4. They walk to the **detector marker** and stand idle on it, facing the detector.
5. Then, for each projection (default **chest PA, LLAT, RLAT**, configurable):
   * **PA**: faces the detector, **hands on hips**, the FOV (collimator) light goes on for 1 s and then off;
   * **LLAT**: turns **right**, **hands on head**, FOV light on for 1 s, then off;
   * **RLAT**: turns **left**, **hands on head**, FOV light on for 1 s, then off.
6. The patient walks back to the door marker and **leaves the room**, ending back outside the entrance.

Isaac Sim's own **behavior system** (`omni.anim.behavior`, Isaac Sim 6.x) produces the motion, so walking, turning and
reaching look natural:

* NVIDIA's human motion library is **retargeted at runtime onto the MPFB rig** that every synthetic human shares,
  using one tag map (`configs/retarget_mpfb.yaml`). The same animation therefore works on every model.
* Walking uses NavMesh path finding along the room's patient route.
* Turns are idles with a facing direction, so the patient turns in place with steps.
* **Hands-on-hip** and **hands-on-head** are behavior-system **custom actions**: pose clips generated at run time on
  the motion library's own skeleton (two-bone IK on top of its standing idle: blend in, hold, blend out). They are
  retargeted onto each patient like any other motion, so the pose fits every body size.

Every visit is **captured** from the room cameras (RGB and depth, `capture.fps` images per second, default 2), into
`run-<timestamp>/SD.xxxxx/<EXAM>/<CAMERA>/RGB`, `/Depth` and `/Depth_Preview` ([10](docs/10_capture.md)). The side-on D455 cameras near the X-ray
machine are split between patients (`LEFT 50 % / RIGHT 50 %`, balanced across runs).

No scene file is written: Isaac builds the stage in memory from the room and human USDs. The record of a visit is a
`timeline.txt` with a timestamp for every patient action.

## Setup

| Item | Version |
|---|---|
| Isaac Sim | 6.2 (tested `6.2.0-rc.14`), path in `configs/isaac.yaml → root` |
| Python (host) | ≥ 3.10 with `pyyaml` (`usd-core` and `pytest` only for the tests). The animation itself runs in Isaac Sim's own Python (`python.sh`), started by the pipeline |
| Network | the motion library is loaded from NVIDIA's content server (`isaac.motion_library`); point the setting at a local copy to run offline |
| Inputs | at least one finished humans run (`output/humans/run-*`) and one rooms run (`output/rooms/run-*`) |

```bash
cd synthetic-data-generation/sdg
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Run

```bash
.venv/bin/python scripts/run_pipeline.py                         # 2 humans x 1 room (latest runs), Isaac GUI
.venv/bin/python scripts/run_pipeline.py --headless              # no window; same animation, faster than real time
.venv/bin/python scripts/run_pipeline.py --humans 5 --rooms 2
.venv/bin/python scripts/run_pipeline.py --human-ids H0003,H0010 --room-ids R0002
.venv/bin/python scripts/run_pipeline.py --humans-root ../output/humans/run-20261019-200423 --rooms-root /data/rooms
.venv/bin/python scripts/run_pipeline.py --projections PA,RLAT   # a subset, in this order
.venv/bin/python scripts/run_pipeline.py --isaac-root /opt/isaac-sim --keep-open
.venv/bin/python scripts/run_pipeline.py --set poses.timing.fov_on_s=2 --set sequence.idle_s.outside=4
.venv/bin/python scripts/run_pipeline.py --dry-run               # inputs + visit plan only, no Isaac Sim
.venv/bin/python scripts/run_pipeline.py -v                      # also show Isaac Sim's own console output
.venv/bin/python scripts/run_pipeline.py --headless --humans 1 --set isaac.debug_capture_dir=/tmp/caps \
    --set isaac.debug_capture_every_n_frames=3                     # record every 3rd frame from 5 cameras for review
```

**Inputs.** With no `root` configured, the pipeline uses the **newest** `run-*` in `output/humans` and in
`output/rooms` that has at least one finished item. A `root` can be a single run directory or a folder of runs.
Without ids, the first N humans and rooms (`count`, default 2 humans and 1 room) are taken in id order.

**Console.** Every step is printed with the simulation time: input resolution, Isaac start, stage build (room,
detector height, motion library, retargeted patient, NavMesh), then each patient action:

```
20:41:07 INFO  === Visit 1/2: SD.00001  human H0001  room R0001  exam CHEST [PA, LLAT, RLAT]
20:41:31 INFO    SD.00001 t=    0.00s  Model loaded outside the room
20:41:33 INFO    SD.00001 t=    2.03s  Model started walking into the check-in room
...
20:42:10 INFO    SD.00001 t=   39.10s  PA: FOV light ON
20:42:11 INFO    SD.00001 t=   40.13s  PA: FOV light OFF
```

**Errors.** Any error is printed as `[ERROR] …` and stops the run. Examples: missing runs or ids, a room without route
anchors, a missing Isaac install, an extension that fails to load, a missing retarget joint, a NavMesh bake failure, a
patient that does not arrive (stuck for `task_timeout_s`), or any exception inside Isaac. The visit is marked
`failed` in `sd_info.json` and Isaac Sim is closed. Exit codes: `0` ok, `1` Isaac or animation error, `2`
configuration or input error.

## Output

```
output/sdg/
└── run-20261021-193000/              one folder per pipeline run (run-<YYYYmmdd-HHMMSS>)
    └── SD.00001/                     one SD = one human (numbered from 1 in every run)
        ├── sd_info.json              human (id, run, USD, height, T7), room(s), exams, Isaac version, status per visit
        └── CHEST/                    one folder per exam (later SPINE/)
            ├── timeline.txt          one line per patient action
            ├── frames.csv            captured frame -> simulated time, step, FOV light
            └── FAR_LEFT/{RGB,Depth,Depth_Preview}/ …   one folder per recorded camera
```

With more than one room, each room gets its own folder: `CHEST/R0001/timeline.txt`, `CHEST/R0002/timeline.txt`.

`timeline.txt`:

```
# sd: SD.00001
# human: H0001 (run-20261019-200423)
# room: R0001 (run-20261020-184851)
# exam: CHEST
# projections: PA, LLAT, RLAT
2026-10-20T20:41:31.204  t=    0.00s  Model loaded outside the room
2026-10-20T20:41:33.240  t=    2.03s  Model started walking into the check-in room
2026-10-20T20:41:37.902  t=    6.70s  Model entered the check-in room
...
2026-10-20T20:42:01.511  t=   30.31s  Model standing on the detector marker, facing the detector
2026-10-20T20:42:03.580  t=   32.37s  PA: Model turning to face the detector (Chest PA)
2026-10-20T20:42:05.212  t=   34.00s  PA: Model moving hands to hands-on-hip pose
...
# status: ok
```

The `t=` value is simulation time since the patient was loaded. The first column is wall-clock time.

## Configure

| File | Controls |
|---|---|
| `configs/run.yaml` | humans / rooms (root, count, ids), exams and their projections, output root, SD name format |
| `configs/sequence.yaml` | spawn distance outside, walk speed, idle time at each point, task timeout, arrival tolerance, FOV light (colour, intensity, cone) |
| `configs/poses.yaml` | projections (facing: detector / left / right / tube, arm pose), arm poses (anchor joint, wrist position, elbow / finger / palm direction), timings (turn, arms up, settle, FOV on 1 s, hold, arms down) |
| `configs/isaac.yaml` | Isaac Sim root, headless, real time, keep open, fps, timeouts, motion library URL, extensions, NavMesh margin |
| `configs/retarget_mpfb.yaml` | MPFB joint → behavior "Human" rig tag map |

**Adding the spine exams later** needs only configuration: define the projections in `poses.yaml` (for example
`T_PA`, `T_LLAT`, `L_PA` with their facing and arm poses), then add `SPINE: [T_PA, T_LLAT, T_RLAT, L_PA, L_LLAT, L_RLAT]`
to `run.yaml → exams`. Each human's SD then gets a `SPINE/timeline.txt` next to `CHEST/`.

## Documentation

1. [Overview & architecture](docs/01_overview.md)
2. [Setup](docs/02_setup.md)
3. [Configuration reference](docs/03_configuration.md)
4. [Running the pipeline](docs/04_running.md)
5. [Animation in Isaac Sim (stage, retarget, NavMesh, poses, FOV light)](docs/05_animation_in_isaac.md)
6. [Output schema (SD, sd_info.json, timeline.txt)](docs/06_output_schema.md)
7. [Logging & errors](docs/07_logging_and_errors.md)
8. [Troubleshooting](docs/08_troubleshooting.md)
9. [Extending (spine exams, new poses, tests)](docs/09_extending.md)
10. [Image capture (cameras, RGB / depth, left-right split, frames.csv)](docs/10_capture.md)

## How it works

`scripts/run_pipeline.py` (host Python):

1. Resolves the humans and rooms.
2. Plans each visit from the room metadata (`anchors.stage.patient_route`, detector normal, entrance outward
   normal) in `sdg_xray/visit.py`.
3. Computes each human's hand targets and T7 height from its metadata.
4. Creates the SD folders.
5. Starts `<isaac root>/python.sh isaac/run_exam.py --job <tmp job.json>` and streams its console.

`isaac/run_exam.py` (inside Isaac Sim), per visit:

| Stage prim | What |
|---|---|
| `/World/Room` | room reference. Detector and tube are set to the patient's T7 height (`room/isaac/compose_scene.py: compose_into`) |
| `/World/HumanMotionLibrary` | NVIDIA motion library (payload) |
| `/World/Patients/<id>` | the human (payload), placed at the start point outside. An identity joint `SkelOrigin` is inserted above MPFB's `root` (pelvis): the retargeter needs `Hips` below a root joint, and the behavior system needs the root at the origin. The name must not be `Root`, because the retargeter compares names case-insensitively and then rejects the skeleton. `BehaviorAgentAPI` is applied, and the rig is retargeted to "Human" with the MPFB tag map and explicit axes (Z up, facing −Y; auto-detection gets MPFB wrong) |
| `/World/NavMeshVolume`, `/World/OutsideFloor` | NavMesh over the suite plus a margin, so the patient can stand and walk outside the entrance. It uses a patient-sized agent (radius 0.12–0.30 m, height 1.8 m, 5 cm sampling). Isaac's defaults (0.5 m radius, 20 cm voxels) close the 0.86 m doors and the narrow check-in room. These are this stage's `navmeshSettings`: your Isaac preferences are not changed |
| `…/TubeHead/FOVLight` | `RectLight` + `ShapingAPI` at the collimator light window, aimed along the beam (TubeHead +Y; a test checks this against the room's beam axis). It is visible only during the FOV-on time |

Before walking, every route segment is checked for a NavMesh path, so a blocked door is reported by name. The patient
is then driven step by step through the agent API:

* `move_to` for each route point, using NavMesh path finding;
* `idle(facing)` for turns in place (idle has no duration and lasts until the next task);
* `custom_action` for the arm poses (pose clips added to the in-memory motion library before Play);
* `cancel_task` only on errors.

Idle animations are limited to the plain `Idle` (`isaac.idle_animation_tags`). Isaac's default set includes
IdleTired, IdleGroove and others.

Each step's result is checked: the task status (with the behavior error code), the arrival distance, the facing after
a turn, and each wrist's offset from the pose anchor. A wrist more than 12 cm from the pose clip's offset (scaled to
the patient) is printed as a warning. `--set isaac.debug_hands=true` prints the wrist offsets, and `--set isaac.debug_capture_dir=<dir>` saves PNG snapshots of each pose.

## Checking it in Isaac Sim

1. `scripts/run_pipeline.py --humans 1 --keep-open` opens the GUI. Watch the patient walk in, pose under the FOV
   light and walk out. Look at the console and at `output/sdg/run-<timestamp>/SD.<n>/CHEST/timeline.txt`.
2. Tune the FOV light brightness once (`sequence.yaml → fov_light.intensity / exposure`), and the hand offsets if a
   pose looks off (`poses.yaml → arm_poses`).
3. `--headless` must give the same timeline (with a faster wall clock).

## Tests

```bash
.venv/bin/python -m pytest -q tests     # config, run discovery, visit plan, pose clips, SD/timeline, retarget joints
```

## Limits

* Walking, turning and idling are NVIDIA's generic human motion. The X-ray arm poses are clips generated from it
  (two-bone IK on the library rig), not motion capture. In the headless test with screenshots (H0001 162.7 cm, H0002
  154.7 cm), both poses looked right, with the torso upright: hands on the hips (PA), and hands on the crown with
  elbows out (LLAT / RLAT). The wrists were within 3–9 cm of the configured pose. Tune `poses.yaml → arm_poses` for
  other body types if needed.
* The humans' anatomical bone meshes are hidden during the animation (`isaac.hide_anatomy`): they are rigidly skinned
  and poke through the skin when the arms are raised.
* A headless visit takes about 80 s (about 50 s of simulated time plus about 30 s of stage set-up).
* Clothing follows the skin (no cloth simulation).
* Doors stay at their sampled opening angles. A very narrow opening can block the NavMesh path, which shows up as
  a "not finished" or "ended … m from the target" error.
