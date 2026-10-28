# 3. Configuration reference

All settings are in `configs/*.yaml`. Any value can be overridden on the command line with
`--set <file>.<key>=<YAML value>`, for example `--set poses.timing.fov_on_s=2` or
`--set run.exams="{CHEST: [PA]}"`. A value of `null` really sets null. The configuration is validated before
anything starts, and errors end the run with exit code 2.

| File | Controls |
|---|---|
| `run.yaml` | inputs (humans, rooms), exams and their projections, output folder |
| `sequence.yaml` | visit route and idle times, walking, hand-IK speed, timeouts, FOV light |
| `poses.yaml` | projections (facing + arm pose), arm-pose hand targets, timing of each projection |
| `isaac.yaml` | Isaac Sim path and mode, motion library, idle animations, NavMesh agent |
| `retarget_zanatomy.yaml` | Z-Anatomy anatomical joint → behavior rig tag map, root joint, skeleton axes |
| `retarget_mpfb.yaml` | MPFB joint → behavior rig tag map, inserted root joint, skeleton axes |
| `capture.yaml` | image capture: cameras, streams, fps ([10](10_capture.md)) |
| `annotations.yaml` | per-frame vertebra / hip / shoulder heights and their overlay in the RGB images |

## 3.1 `run.yaml`

| Key | Default | Meaning |
|---|---|---|
| `humans.root` | `null` | a humans run dir (`run-*`) or a folder of runs. `null` = `<repo>/output/humans` |
| `humans.count` | `2` | the first N finished humans of the run (ignored with `ids`) |
| `humans.ids` | `null` | explicit list, e.g. `[H0001, H0007]` |
| `rooms.root` / `count` / `ids` | `null` / `1` / `null` | the same for rooms (`<repo>/output/rooms`) |
| `exams` | `{CHEST: [PA, LLAT, RLAT]}` | exam name → ordered projections. One exam = one visit and one folder in the SD |
| `output_root` | `null` | folder for the run folders. `null` = `<repo>/output/sdg` |
| `run_dir_format` | `"run-%Y%m%d-%H%M%S"` | name of each run's folder (strftime); SDs go to `<output_root>/<run>/SD.<n>` |
| `sd_id_format` | `"SD.{:05d}"` | SD folder name. Numbers start at 1 in every run |

"Finished" means status `ok` or `warn` in the run's `results.json`. With a folder of runs, the **newest** `run-*` (by
name, i.e. timestamp) that has at least one finished item is used.

## 3.2 `sequence.yaml`

| Key | Default | Meaning |
|---|---|---|
| `start_outside_m` | `1.5` | spawn distance in front of the entrance door, along its outward normal |
| `walk_speed_mps` | `null` | `null` = the behavior system's natural speed; else a fixed walking speed |
| `idle_s.outside` | `2.0` | standing outside after being loaded |
| `idle_s.check_in` | `0.0` | pause in the check-in room (0 = walk straight through) |
| `idle_s.entrance_marker` | `2.0` | idle on the entrance marker |
| `idle_s.detector_marker` | `1.5` | idle on the detector marker, facing the detector, before the first projection |
| `idle_s.exit_marker` | `1.0` | idle on the door marker on the way out |
| `idle_s.end` | `1.5` | standing outside at the end |
| `task_timeout_s` | `90` | a walk that takes longer is an error (patient stuck) |
| `arrive_tolerance_m` | `0.25` | a walk that ends further from its target than this is an error |
| `outside_light.enabled` | `true` | corridor light above the arrival area outside the entrance (a copy of one of the room's ceiling panels: size, intensity, colour temperature) |
| `outside_light.height_m` / `towards_door_m` / `intensity_scale` | `2.6` / `0.6` / `1.0` | its height, offset from the spawn point towards the door, brightness factor |
| `fov_light.enabled` | `true` | collimator field light |
| `fov_light.color` | `[1.0, 0.96, 0.82]` | RGB |
| `fov_light.intensity` / `exposure` | `60000` / `0.0` | UsdLux RectLight intensity in nits; tune once in Isaac |
| `fov_light.size_m` | `[0.06, 0.06]` | emitting window |
| `fov_light.cone_angle_deg` / `cone_softness` | `9.0` / `0.1` | ShapingAPI cone (about 35 × 43 cm at 1.5 m SID) |

## 3.3 `poses.yaml`

### Projections

```yaml
projections:
  PA:   {facing: detector, arms: hands_on_hip,  label: "Chest PA"}
  LLAT: {facing: right,    arms: hands_on_head, label: "Chest left lateral"}
  RLAT: {facing: left,     arms: hands_on_head, label: "Chest right lateral"}
```

| Field | Values |
|---|---|
| `facing` | `detector` (PA), `left` (90° left from facing the detector, right side on the detector), `right` (90° right, left side on the detector), `tube` (back to the detector, AP) |
| `arms` | a key of `arm_poses` |
| `label` | text used in the timeline |

### Arm poses

Arm poses are played as behavior-system **custom actions**. At run time each pose becomes a short clip on the motion
library's own skeleton (NVIDIA "Human" rig), built from its standing `Idle`: blend in, hold, blend out. The clip is
retargeted onto every patient like any other motion, so the pose scales with the body and the legs and torso keep a
natural idle ([05 §5.6](05_animation_in_isaac.md#56-arm-poses)).

Values are in the **motion library frame**, in cm: +X = the patient's left, +Y = up, +Z = front. The library rig is
about 1.8 m tall.

```yaml
arm_poses:
  hands_on_hip:                       # PA chest: back of the hands on the hips, palms facing out, elbows out and forward
    anchor: Pelvis
    left: {wrist_cm: [21, 10, -3], elbow: [1, 0, 0.4], fingers: [0.15, -1, -0.25], palm: [1, 0, -0.3]}
  hands_on_head:                      # laterals: hands on the crown, fingers interlaced, elbows out to the sides
    anchor: Head
    left: {wrist_cm: [10, 12, -4], elbow: [1, 0.2, -0.2], fingers: [-1, 0.2, 0], palm: [0, -1, 0]}
    via: {wrist_cm: [42, -8, 4], elbow: [0.6, -1, 0], fingers: [0, 1, 0], palm: [0, 0, 1]}
```

| Field | Meaning |
|---|---|
| `anchor` | library joint the wrist position is relative to (`Head`, `Pelvis`, `Chest`, `Neck1`, `Spine1`, …) |
| `left` | left arm. The right arm mirrors it (X negated) unless a `right` entry is given |
| `wrist_cm` | wrist position relative to the anchor, in cm (required) |
| `elbow` | direction the elbow points: the bend direction of the two-bone IK (default out and back) |
| `fingers` | wrist → fingers direction |
| `palm` | palm normal: the side the palm faces |
| `via` | optional intermediate arm pose (same fields) passed halfway on the way in and out. Hands-on-head uses a "goal post" (arms out to the sides, elbows bent, hands up) |

### Timing (per projection)

| Key | Default | Phase |
|---|---|---|
| `turn_s` | `1.6` | minimum turn time; the turn continues until the patient faces the target within 8° |
| `after_turn_s` | `0.4` | settle after the turn |
| `arms_up_s` | `1.4` | blend from the idle into the pose (the clip's ActionStart) |
| `settle_s` | `0.8` | still, before the FOV light |
| `fov_on_s` | `1.0` | FOV light on |
| `hold_after_s` | `0.5` | still, after the FOV light |
| `arms_down_s` | `1.2` | blend back to the idle (the clip's ActionEnd) |
| `between_s` | `1.0` | idle before the next projection |

## 3.4 `isaac.yaml`

| Key | Default | Meaning |
|---|---|---|
| `root` | `/home/gehc-1/Joseph/NVIDIA/isaac-sim` | Isaac Sim install |
| `python` | `python.sh` | launcher inside `root` |
| `headless` | `false` | `true` = no window. `--headless` / `--gui` override it |
| `viewport_camera` | `CeilingCam_FarLeft` | GUI: the room camera the viewport looks through (`null` = Isaac's default view) |
| `realtime` | `true` | GUI: play at wall-clock speed (headless always runs as fast as possible) |
| `keep_open` | `false` | GUI: stay open after the last visit until the window is closed |
| `fps` | `30` | simulation frames per second (fixed time step) |
| `debug_hands` | `false` | at each pose, print each wrist's offset from the anchor and the clip's intended offset |
| `debug_capture_dir` | `null` | folder: PNG snapshots of the patient at each pose (side D455 colour camera, ceiling camera, a camera behind the patient) |
| `debug_capture_every_step` | `false` | with `debug_capture_dir`: also capture after every step (walking, idles) |
| `debug_capture_every_n_frames` | `0` | with `debug_capture_dir`: > 0 saves every n-th frame of the whole visit from all capture cameras |
| `hide_body_under_clothes` | `true` | remove the body faces fully covered by garments, so skin cannot poke through the clothes in poses |
| `clothing_reach_m` | `0.07` | skin counts as covered when a garment lies within this distance outside it (loose sleeves sit 5–6 cm out) |
| `hide_anatomy` | `true` | hide the humans' `bone_*` anatomical skeleton meshes (rigidly skinned, they poke through the skin in arm poses) |
| `startup_timeout_s` | `600` | motion library loading |
| `run_timeout_s` | `3600` | whole Isaac run; the process is terminated after this |
| `motion_library` | NVIDIA content URL | HumanMotionLibrary USD |
| `motion_library_rig` | `Human` | retarget rig of the motion library |
| `retarget_maps` | `zanatomy_anatomical: retarget_zanatomy`, `default: retarget_mpfb` | rig id (`<id>.json → skeleton.rig`) → retarget config. `default` serves any other rig and humans without a rig id. Every value must be a `retarget_*.yaml` in the config folder |
| `idle_animation_tags` | `[Idle]` | allowed idle variations. Isaac's default set also has IdleTired (stooped), IdleGroove, IdleTaunt, … |
| `extensions` | navigation, retarget, behavior, graph | enabled at start-up |
| `navmesh.margin_m` | `3.0` | NavMesh volume = room bounds + margin (covers the area outside the entrance) |
| `navmesh.height_m` | `2.4` | volume height |
| `navmesh.agent_min_radius_m` / `agent_max_radius_m` | `0.12` / `0.3` | NavMesh agent radii. The maximum must be ≥ the agent's radius (about 0.22–0.24 m) |
| `navmesh.agent_min_height_m` | `1.8` | clearance height |
| `navmesh.agent_max_step_height_m` | `0.15` | |
| `navmesh.agent_min_island_radius_m` | `0.2` | smaller walkable islands are dropped |
| `navmesh.sampling_distance_m` | `0.05` | voxel size. Isaac's 0.2 m default closes the narrow check-in room |

## 3.5 Retarget maps: `retarget_zanatomy.yaml`, `retarget_mpfb.yaml`

Each human is retargeted with the map of its rig (`isaac.retarget_maps`). The log line
`Human H0001: rig zanatomy_anatomical -> retarget_zanatomy.yaml` shows the choice. Both files have the same keys.

`retarget_zanatomy.yaml` (the default humans: mpfb-humans skeleton layer `zanatomy`):

| Key | Default | Meaning |
|---|---|---|
| `root_joint_name` | `SkelOrigin` | already the top joint of these humans (nothing is inserted) |
| `up_axis` / `forward_axis` | `Z` / `MINUS Y` | skeleton facing, set explicitly |
| `tags` | 61 entries | Hips → pelvis; Spine1 / Spine2 / Chest → vertebra_L4 / vertebra_L1 / vertebra_T7; Neck1 / Neck2 / Head → vertebra_C7 / vertebra_C4 / skull; Shoulder / Arm / ForeArm / Hand → clavicle / humerus / ulna / carpus; Leg / Shin / Foot / ToeBase → femur / tibia / talus / proximal_phalanx3_foot; fingers → metacarpal / proximal / middle / distal phalanges. No eye tags (the rig has no eye joints) |

Untagged joints keep their rest pose relative to their parent: the vertebrae between the tagged levels, the scapula
(under the clavicle) and the radius (under the ulna). Before the retarget, sdg checks that the tagged joints form
chains down the skeleton (`sdg_xray/rig.py check_tag_chains`). If the spine bends too stiffly, the Spine and Chest
levels are the setting to change.

`retarget_mpfb.yaml` (MPFB default rig: skeleton layers `procedural` / `none`, and humans built before the Z-Anatomy
rig):

| Key | Default | Meaning |
|---|---|---|
| `root_joint_name` | `SkelOrigin` | identity joint inserted above MPFB's `root`. It **must not** be `root` in any case (see [05](05_animation_in_isaac.md)) |
| `up_axis` / `forward_axis` | `Z` / `MINUS Y` | MPFB skeleton facing, set explicitly (auto-detection is wrong for MPFB) |
| `tags` | 63 entries | behavior rig tag → MPFB joint leaf name (Hips → root, Spine1 → spine04, Chest → spine01, LeftArm → upperarm01_L, LeftHand → wrist_L, fingers, …) |

## 3.6 Command line

| Flag | Same as |
|---|---|
| `--humans N` / `--rooms N` | `run.humans.count` / `run.rooms.count` |
| `--human-ids H0001,H0003` / `--room-ids R0002` | `run.humans.ids` / `run.rooms.ids` |
| `--humans-root DIR` / `--rooms-root DIR` | `run.humans.root` / `run.rooms.root` |
| `--exam CHEST` | run only this exam of `run.exams` |
| `--projections PA,RLAT` | projections (in this order) for the single exam |
| `--output-root DIR` | `run.output_root` |
| `--isaac-root DIR` | `isaac.root` |
| `--headless` / `--gui` | `isaac.headless` true / false |
| `--keep-open` | `isaac.keep_open: true` |
| `--no-capture` | `capture.enabled: false` |
| `--no-overlay` | `annotations.overlay.enabled: false` (clean RGB images; the annotation JSON is still written) |
| `--set KEY=VALUE` | any key, repeatable |
| `--dry-run` | resolve inputs and print the plan; Isaac is not started and no SD folder is created |
| `-v`, `--verbose` | also print Isaac Sim's own console output |
| `--config DIR` | another config folder |

## 3.7 `annotations.yaml`

Per captured frame, `annotations/<frame>.json` holds heights in cm above the room floor, and the same points are drawn
into the RGB images ([10.5](10_capture.md#105-anatomy-annotations)). This needs Z-Anatomy humans (`rig
zanatomy_anatomical`). Humans with another rig get no annotations, and a warning is logged per human.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | write `annotations/<frame>.json` (only while capturing) |
| `ndigits` | `1` | decimals of the cm values |
| `vertebrae` | `[C1 … L5]` (24) | vertebra levels. Point = mid-point of the vertebra (bounding-box centre of its bone mesh), moving with joint `vertebra_<level>` |
| `mesh_prefix` | `bone_vertebra_` | name of the vertebra bone mesh: `<mesh_prefix><level>` |
| `landmarks.hip.left/right` | `greater_trochanter_l/r` on `femur_L/R` | hip point (`point` = a key of `<id>.json → anatomy.points_m`, `joint` = the bone it moves with) |
| `landmarks.shoulder.left/right` | `acromion_l/r` on `scapula_L/R` | shoulder point |
| `overlay.enabled` | `true` | draw the points into `RGB/<frame>.png`. **With the overlay on, the RGB images are not clean training images.** `--no-overlay` turns it off |
| `overlay.marker_radius_px` | `4` | dot radius at 720 px image height (scaled with the image height) |
| `overlay.font_size_px` | `14` | label size at 720 px image height |
| `overlay.label_vertebrae` | `all` | `all` or `every_2nd` (every vertebra gets a dot either way) |
| `overlay.frame_number` | `true` | `frame 000123` in the top-left corner |
| `overlay.colors` | yellow / cyan / magenta / white | `vertebrae`, `hip`, `shoulder`, `text` as `[r, g, b]` |
