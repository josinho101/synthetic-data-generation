# 5. Animation in Isaac Sim

Everything in this chapter runs in `isaac/run_exam.py` inside Isaac Sim 6.2.

## 5.1 Start-up (once per run)

1. `SimulationApp({"headless": …})` starts.
2. Session settings: idle animations are limited to `isaac.idle_animation_tags` (`[Idle]`), and NavMesh auto re-bake
   and visualization are turned off. Auto re-bake would bake the NavMesh again on every stage change, including over
   the high-poly human while it loads, which stalls Isaac for many minutes.
3. The extensions in `isaac.extensions` are enabled. A failure ends the run.
4. A listener records the error code of every ended behavior task, so errors can name the reason.

## 5.2 Stage per visit

A new in-memory stage (Z up, meters) is created for every visit:

| Prim | Built by | What |
|---|---|---|
| `/World/Room` | `compose_scene.compose_into()` | reference to `<room>.usd`. `WallStand/Carriage` and the tube arm are set to the patient's **T7 height**, clamped to the travel limits. D455 Top/Front cameras move with them |
| `/World/HumanMotionLibrary` | payload of `isaac.motion_library` | NVIDIA's human motions (walk, turn, idle, …) |
| `/World/Patients/<id>` | payload of `<human>.usd` | the patient, placed at the start point and facing the door **before Play**, so the agent is created there |
| `/World/NavMeshVolume` | `CreateNavMeshVolumeCommand` | include volume = room bounds + `navmesh.margin_m`, height `navmesh.height_m` |
| `/World/OutsideFloor` | mesh with a collider | walkable ground outside the suite (the NavMesh is baked from collision geometry) |
| `…/TubeHead/FOVLight` | `UsdLux.RectLight` + `ShapingAPI` | collimator field light ([5.7](#57-fov-light)) |

## 5.3 Making the MPFB human a behavior agent

The synthetic humans use the MPFB default rig (247 joints, including `LM_*` landmark joints and face joints). The
motion library is authored for NVIDIA's "Human" rig (81 joints, T-pose). Six steps make them compatible. They work on
the in-memory stage only; the human USD is not changed.

1. **Identity root joint.** MPFB's top joint `root` sits at the pelvis (about 0.88 m). The retargeter needs the
   `Hips` tag *below* a root joint, and the behavior system needs the skeleton root at the origin. So a joint
   `SkelOrigin` with an identity transform is inserted above it. The script updates the joint list, bind and rest
   transforms, `primvars:blender:bone_lengths`, and every skinned mesh's `skel:joints`.

   The name must not be `Root`: the retargeter treats `Root` and MPFB's `root` as the same name and then rejects the
   skeleton ("RetargetController: Invalid input skeletons").
2. **Behavior agent.** The SkelRoot gets the `BehaviorAgentAPI`, its `behavior:motionLibrary` targets
   `/World/HumanMotionLibrary`, and `NavMeshExcludeAPI` keeps the human out of the NavMesh.
3. **Retarget.** `RetargetRig("Human")` uses the tag map from `retarget_mpfb.yaml` (63 tags), and the axes are set
   explicitly to **up Z, forward −Y**. Then `auto_setup(auto_facing=False, auto_tagging=False, auto_posing=True)`
   prepares the rig. Isaac's automatic facing picks +Y forward for MPFB, which flips the character for the
   behavior system (negative agent height). Automatic tagging does not know MPFB joint names and can crash Isaac.
4. **Retarget pose = the reference T-pose.** Motions are transferred relative to each rig's *retarget pose*, so both
   rigs must stand in the same posture there. The reference rig stands in a T-pose. MPFB humans rest in an A-pose
   (arms about 45° down, forearms angled forward), and Isaac's auto-posing leaves that unchanged. Every motion then
   came out with raised, bent forearms (idle "presenting" arms). The script therefore authors
   `controlRig:retargetTransforms` itself:
   * it reads the reference skeleton (`omni.anim.retarget.core/data/rigs/Human/assets/human_skeleton.usd`; joint
     names via its `automap/Default.automap.json`);
   * it rotates each tagged MPFB segment onto the reference direction: clavicle → upper arm → forearm → hand →
     middle finger, and the legs down to the toes;
   * it rolls each hand so the palm (index → pinky knuckles) matches.

   Spine and neck are left as authored; re-aiming them tilted the head back. The log line
   `retarget pose = reference T-pose (largest segment deviation 0.0 deg)` confirms the result.
   *Steps 1, 5 and 6 belong to the human model and are done by the humans pipeline at export (`usd_post`: `SkelOrigin`
   root joint, anatomy `purpose = guide`, clothing `holeIndices`). sdg only applies them to humans built before that
   (log: `the human model already hides … body faces under its clothing`).*
6. **Skin under clothing removed.** Body and garments are skinned to the same skeleton with different weights, so in
   raised-arm and hands-on-hip poses the skin pushed through close-fitting cloth (skin-coloured "gaps" in the shirt).
   `sdg_xray/clothing.py` casts a short ray along each body vertex normal on the rest pose. If it hits one of the
   human's garments (`<id>.json → clothing.items[].asset`) within `isaac.clothing_reach_m` (7 cm), the vertex is
   covered. Body faces whose vertices are all covered are removed from the body mesh, with their face-varying UVs,
   in the in-memory stage. This is MakeHuman's delete-group idea. Skin at hems, collars and sleeve openings stays. Log:
   `4195/13378 body faces under clothing hidden (…)`.
5. **Anatomy hidden.** The humans carry a schematic anatomical skeleton (`bone_*` meshes, about 80 bones) for later
   X-ray-style use. The bones are skinned rigidly to single joints while the skin deforms smoothly, so at raised arms
   they poke through the shoulders and armpits. They are made invisible (`isaac.hide_anatomy: true`).

After Play the script waits for the agent and checks that the agent height is between 0.5 and 2.5 m (it was 1.69 m and
1.57 m for H0001 and H0002), and that the agent radius fits the NavMesh.

## 5.4 NavMesh

The NavMesh is baked once per visit (`start_navmesh_baking_and_wait`) with patient-sized settings. These are written
to the stage's `customLayerData.navmeshSettings` and the session settings (in cm), never to saved preferences:

| Setting | Value | Isaac default | Why |
|---|---|---|---|
| agent radius | 0.12–0.30 m | 0.20–0.50 m | 0.5 m blocks the 0.86 m connecting door and the half-open entrance |
| sampling (voxel) | 0.05 m | 0.20 m | the check-in room (≈1.34 × 1.34 m, bench on one side, gown shelf at 1.3 m on the other) leaves a ≈0.65 m strip |
| min height | 1.8 m | 2.0 m | |
| min island radius | 0.2 m | 2.0 m | |
| max step height | 0.15 m | 0.25 m | the bench (0.46 m) must stay an obstacle |

**Route check.** Before the patient moves, every route point must lie on the NavMesh (within 0.25 m), and every
segment start → entrance → check_in → connecting_door → entrance_stand → patient_stand → … → outside must have a
NavMesh path that ends within 0.3 m of its target. Otherwise the visit fails with the name of the blocked segment.

## 5.5 Steps and the behavior API

The visit plan (`sdg_xray/visit.py`) is a list of steps. Each is executed with the agent API (`omni.anim.behavior.core`):

| Op | API | Behaviour and checks |
|---|---|---|
| `spawn` | prim placed before Play (`teleport` if the agent ends up elsewhere) | the patient must be within 0.3 m of the start point |
| `idle` | `idle(facing)`, then step `duration` frames | `idle` has no duration in Isaac 6.2: it lasts until the next task. While a pose is held (`keep_arms`) no new task is started, so the pose action keeps running |
| `walk` | `move_to(point, auto_brake=last)` for each route point | NavMesh path finding goes around door leaves and furniture, and the agent only brakes at the last point. The task must succeed within `task_timeout_s`, and the walk must end within `arrive_tolerance_m` |
| `turn` | `idle(facing)` | waits at least `turn_s` and until the facing error is ≤ 8° (an error after `turn_s + 10 s`), then settles `after_turn_s` |
| `arms` (pose) | `custom_action(action="Xray…", duration=settle + FOV on + hold)` (the duration counts after the clip's blend-in) | plays the pose clip: blend in, hold through the FOV light. A rejected or failed action is an error |
| `arms` (down) | (waits) | waits until the action has played its blend-out (ActionEnd), at most `arms_down_s + 5 s` |
| `fov` | light visibility | before the light goes on, the hand positions are checked again |

`move_along` (one polyline) is not used: it follows the straight lines between the waypoints and fails at the
half-open entrance door. `move_to` per point plans a path on the NavMesh instead.

## 5.6 Arm poses

Isaac's `reach_hand` is a whole-body reach for grabbing objects. Tried first, it could not hold an X-ray posture: the
torso leaned and twisted, and the hands ended 11–25 cm off. The poses are therefore **custom actions**: motion clips
in the motion library, the same mechanism NVIDIA uses for its own actions. No external motion capture is involved.
The clips are generated at the start of each run by `sdg_xray/pose_clips.py`:

1. Start from frame 0 of the library's own `BuiltinActions/Idle/Idle` clip (a natural standing body).
2. Two-bone IK per arm on the library skeleton: the wrist goes to `anchor + wrist_cm`, the elbow bends towards
   `elbow`, and the hand turns to `fingers` / `palm` ([03 §3.3](03_configuration.md#arm-poses)). The right arm mirrors
   the left.
   The palm's turn (pronation / supination) is shared between a forearm roll and the wrist like in a real arm: the
   roll that minimises the wrist's turn is searched (5° steps) and the forearm takes `forearm_roll_share` (0.6) of it.
   With the whole turn on the wrist, one wrist twisted up to 120° and the skin wrung ("candy wrapper").
3. The clip runs at 30 fps:

   | Frames | Content | Annotation (track) |
   |---|---|---|
   | `[0, arms_up_s]` | blend from the idle into the pose: per-joint slerp along the shorter arc, through the `via` pose halfway if given, so both arms move as mirror images | `ActionStart` (3) |
   | then 2 s | hold the pose. Legs, torso and head keep playing the Idle, so the patient is not frozen | `ActionLoop` (2) |
   | `[…, + arms_down_s]` | blend back to the idle | `ActionEnd` (4) |
   | whole clip | action name `XrayHandsOnHip` / `XrayHandsOnHead` | name (1) |

   The prim `/Root` (`SkelAnimation`) carries `BehaviorActionAPI` (`behavior:action:name`) and
   `AnimationSkelBindingAPI`.
4. The clips are written to a temporary folder (deleted at the end of the run) and registered in each visit's
   in-memory motion library under `CustomActions/Xray/`, with `animationSkelBinding:sourceSkeleton` pointing at the
   library skeleton, **before Play**, when the agent reads its actions. Nothing is written to Isaac's user
   custom-action folder.
5. The agent plays a pose with `custom_action(action, duration)`. The behavior system retargets it onto the MPFB
   patient through the retarget pose of [5.3](#53-making-the-mpfb-human-a-behavior-agent), so the pose scales with
   the body.

**Check.** After the blend-in, and again when the FOV light goes on, each wrist's offset from the anchor joint (`Head`
or `Hips`) is compared with the clip's offset, scaled by the patient's head height. More than 12 cm off is printed as a
warning. `--set isaac.debug_hands=true` prints both offsets.

Measured in the headless test with screenshots (H0001 162.7 cm, H0002 154.7 cm):

| Pose | Result |
|---|---|
| idle / walking | arms hang naturally, head level |
| hands on hip (PA) | hands on the hips, elbows out and back. The wrists are 3–9 cm from the clip offset |
| hands on head (LLAT, RLAT) | hands on the crown, elbows out to the sides, torso upright. The wrists are 3–8 cm from the clip offset; no warnings |

**Debug captures.** `--set isaac.debug_capture_dir=<folder>` writes PNGs at every pose from `CeilingCam_FarLeft`, the
D455 colour cameras (Left, Right, Front) and `follow`, a close camera that tracks the patient from the room-centre
side. Frames go to `<folder>/<SD>_<exam>_<room>/<camera>/<n>_t<sim time>_<step>.png`. For a full recording of the
visit, add `--set isaac.debug_capture_every_n_frames=3` (every 3rd frame, about 520 frames per camera for a chest
visit); `debug_capture_every_step=true` captures after every step instead.

## 5.7 FOV light

Rooms now carry the light themselves (`Collimator/FOVLight`, room pipeline): sdg only switches its visibility on for
`fov_on_s` and off again (log: `collimator FOV light from the room`). For rooms built before that, sdg adds the same
light (DiskLight + IES rectangle, `sequence.yaml → fov_light`). `fov_light.intensity_override` changes the room
light's brightness for a run. The description below is the earlier sdg-only light, kept for reference.

### Earlier sdg-only light (rooms without FOVLight)

* `UsdLux.RectLight` at the centre of `…/Collimator/LightWindow` (computed in the TubeHead frame), 1 cm in front of
  it, rotated +90° about X so it emits along TubeHead **+Y = the beam axis**. A unit test checks +Y against the room's
  `anchors.stage.beam_axis`.
* `ShapingAPI` cone (9° half-angle by default) gives a field of about 35 × 43 cm at 1.5 m SID.
* The light is created invisible and made visible only between `FOV light ON` and `FOV light OFF` (`fov_on_s`, 1 s).
* Because it is a child of TubeHead, it moves with the tube when the tube is set to the patient's T7 height.

## 5.8 Time

* The timeline plays with `useFixedTimeStepping`, `play_every_frame` and `fps` (30) time codes per second, so every
  app update advances exactly 1/30 s of simulated time. GUI and headless therefore produce the same motion.
* GUI real-time mode sleeps between frames to match the wall clock.
* `timeline.txt` records `t =` simulated seconds since the patient was loaded, plus the wall-clock time.
