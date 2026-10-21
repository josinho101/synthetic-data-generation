# 7. Logging & errors

## 7.1 Console

The console is the run log. No log files are written; `timeline.txt` is the per-visit record. To keep a run log,
redirect it: `... run_pipeline.py --headless 2>&1 | tee run.log`.

Every line is `HH:MM:SS LEVEL message`:

```
21:19:14 INFO  Humans: H0001, H0002 from .../output/humans/run-20261019-200423
21:19:14 INFO  Rooms:  R0001 from .../output/rooms/run-20261020-184851
21:19:14 INFO  Visit plan R0001 / CHEST (38 steps):
21:19:14 INFO    01 spawn                                   Model loaded outside the room
...
21:19:14 INFO  Output: .../output/sdg/run-20261021-211914
21:19:14 INFO  SD.00001 <- human H0001
21:19:14 INFO  Starting Isaac Sim 6.2.0-rc.14 (headless mode): .../python.sh .../isaac/run_exam.py --job /tmp/xray_job_....json
21:19:28 INFO  === Visit 1/2: SD.00001  human H0001  room R0001  exam CHEST [PA, LLAT, RLAT]
21:19:29 INFO  stage: detector and tube at 1.2499 m (patient T7)
21:19:32 INFO  stage: motion library loaded
21:19:32 INFO    pose clip XrayHandsOnHip: 138 frames, hold [42, 102], wrists L (17, 12, -2) R (-17, 12, -2) cm from Pelvis
21:19:32 INFO    pose clip XrayHandsOnHead: 138 frames, hold [42, 102], wrists L (10, 12, -4) R (-10, 12, -4) cm from Head
21:19:32 INFO  stage: pose actions XrayHandsOnHip, XrayHandsOnHead added to the motion library
21:19:32 INFO  stage: 166 anatomical bone meshes hidden (isaac.hide_anatomy)
21:19:32 INFO  stage: retarget pose = reference T-pose (largest segment deviation 0.0 deg)
21:19:32 INFO  stage: patient H0001 (162.65 cm) is a behavior agent
21:19:33 INFO  stage: NavMesh baked
21:19:33 INFO  stage: NavMesh route checked (10 segments)
21:19:42 INFO  agent ready: height 1.69 m, radius 0.24 m, arm length 0.45 m
21:19:42 INFO  SD.00001 t=    0.00s  Model loaded outside the room
...
21:20:44 INFO  SD.00001 CHEST done: 49.9 s simulated -> .../run-20261021-211914/SD.00001/CHEST/timeline.txt
21:21:56 INFO  Isaac Sim exited with code 0 after 162 s
21:21:56 INFO  SD.00001: ok (CHEST/R0001 ok)
21:21:56 INFO  Done in 162 s: 2 SD ok, 0 failed -> .../output/sdg/run-20261021-211914
```

| Source | Shown |
|---|---|
| host pipeline | always |
| `run_exam.py` (lines it prints with the `[xray]` prefix; the prefix is removed) | always |
| Isaac's own output | only with `-v`, except lines with `[Error]` and Python tracebacks, which are always shown (indented, `isaac | …`) |

## 7.2 Warnings (the run continues)

| Message | Meaning |
|---|---|
| `warning: <pose>: wrists left 0.14 m, right 0.13 m from the pose` | after the blend-in, a wrist is more than 12 cm from the pose clip's offset (scaled to the patient) |
| `warning: <pose> at FOV on: wrists …` | the same check, when the FOV light goes on |

## 7.3 Errors (the run stops)

Any error prints `[ERROR] …`. Inside Isaac, the failing visit gets `ERROR: …` and `# status: failed` in its timeline
and `status: failed` with the message in `sd_info.json`. Isaac is then closed and the pipeline exits with code 1.
Later visits are not run.

| Stage | Error (example) | Exit |
|---|---|---|
| config | `[ERROR] [config] run.exams.CHEST: projection 'XLAT' is not defined in poses.yaml` | 2 |
| inputs | `no finished humans run in …`, `2 humans requested but … has only 1 finished`, `humans H9999 not found (or not ok) in …` | 2 |
| inputs | `room R0001: anchors.stage lacks [...] (regenerate the room with the current room pipeline)` | 2 |
| inputs | `human H0001: no T7 / chest landmarks in …` | 2 |
| config | `poses.arm_poses.hands_on_head.left.wrist_cm must be [x, y, z]` | 2 |
| Isaac | `Isaac Sim not found: /path (set isaac.root …)` | 2 |
| Isaac | `extension omni.anim.behavior.core could not be enabled` | 1 |
| stage | `motion library …: not loaded after 600 s`, `human H0001: expected 1 SkelRoot and 1 Skeleton …` | 1 |
| retarget | `retarget joints missing in the skeleton: …`, `retarget set-up (retarget pose) failed`, `only 40/63 retarget tags applied` | 1 |
| agent | `behavior agent … was not created`, `behavior agent height -1.70 m is implausible (retarget up/forward axes wrong?)`, `agent radius 0.32 m exceeds isaac.navmesh.agent_max_radius_m` | 1 |
| NavMesh | `NavMesh baking failed`, `route point check_in (…) is not on the NavMesh (nearest walkable …)`, `no NavMesh path from … to … (door too narrow / blocked?)` | 1 |
| motion | `walk to check_in (point 1/2 at 1.61, -4.16): task ended with BehaviorTaskStatus.FAILED (error …) at (x, y)` | 1 |
| motion | `walk to …: not finished after 90 s (patient stuck at …)`, `walk to …: ended 0.42 m from the target` | 1 |
| motion | `turn: still 35 deg off after 11 s` | 1 |
| poses | `arm pose hands_on_head: anchor joint 'Head2' not in the motion library skeleton`, `motion library Idle clip: not loaded` | 1 |
| poses | `hands_on_head: custom action XrayHandsOnHead was rejected (known actions: […])`, `arms down: pose action still running after 6 s` | 1 |
| app | `Isaac Sim window was closed`, any Python exception (with traceback) | 1 |
| launcher | `Isaac run exceeded isaac.run_timeout_s = 3600 s, terminating` | 124 |

`SimulationApp.close()` can end the Isaac process with code 0 before the script's own exit code is set. The launcher
therefore also counts `[ERROR]` lines and reports 1 if there were any.

## 7.4 Debug options

| Option | Prints |
|---|---|
| `-v` | Isaac's own console output (extension start-up, warnings) |
| `--set isaac.debug_hands=true` | at each arm pose: each wrist's offset from the anchor joint, next to the pose clip's offset |
| `--set isaac.debug_capture_dir=DIR` | PNG snapshots at each pose (side D455 colour camera, ceiling camera, a camera behind the patient); with `isaac.debug_capture_every_step=true` after every step |
| `--dry-run` | the resolved inputs and the full step plan |
