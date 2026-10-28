# 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| First run: nothing happens for minutes after `Starting Isaac Sim`, GPU idle | RTX shader compilation on a cold cache | wait. Later starts take about 15 s |
| Isaac hangs while the human loads (CPU busy, GPU idle) | NavMesh auto re-bake running over the human mesh | the script disables it (`autoRebakeOnChanges`). If you changed the script, keep that setting before any NavMesh volume exists |
| `RetargetController: Invalid input skeletons` / `Tag 'Hips' is not found when building a chain` | no root joint above Hips, or the inserted joint is named `Root` | keep `retarget_mpfb.root_joint_name: SkelOrigin` (any name except `root` in any case) |
| `retarget joints of retarget_zanatomy.yaml missing in the skeleton` | the human's rig differs from the map chosen for its `skeleton.rig` | check `isaac.retarget_maps`; rebuild the humans with the current mpfb-humans |
| `tagged joints do not form chains (LeftHand (carpus_L) is not below LeftForeArm (ulna_L) …)` | Z-Anatomy human built before mpfb-humans `rig_parent_overrides` (radius and ulna both under the humerus: the forearm skin would tear at the elbow) | rebuild the humans |
| `warning: annotations: … vs agent …: N cm (warning: > 2 cm)` | the skeleton pose read through Fabric differs from the agent's own joints | report it; the annotation heights of that run are not reliable |
| `Human H0001: no vertebra bones (rig mpfb_default): no annotations` | MPFB-rig human | use Z-Anatomy humans (mpfb-humans `skeleton.layer: zanatomy`) |
| Annotation labels cover the patient in the RGB images | the overlay is on (default) | `--no-overlay` for clean images, or `overlay.label_vertebrae: every_2nd` |
| `behavior agent height -1.70 m is implausible` / the patient walks in random directions | retarget axes auto-detected wrong | keep `up_axis: Z`, `forward_axis: MINUS Y` |
| Isaac crashes right after Play | a character with a failed retarget | fix the retarget error above; never apply Isaac's automatic tagging to the humans |
| `NavMesh baking failed` | the volume was not registered yet, or there is no walkable collision geometry | the script waits 10–20 updates and retries. Check that the room has colliders (`room export.physics.colliders: true`) |
| `walk to …: task ended with FAILED` right after the start, the patient does not move | `navmesh.agent_max_radius_m` is smaller than the agent radius | keep the maximum ≥ 0.3 m (the agent radius is printed in `agent ready`) |
| `no NavMesh path from check_in … ` / `route point … is not on the NavMesh` | a door or the check-in room is too narrow for the NavMesh settings | lower `agent_min_radius_m` or `sampling_distance_m`, or regenerate the room with wider doors or a larger check-in room (room `room.yaml`) |
| The patient stops at the entrance door | the entrance leaf at a small opening angle blocks the path | raise the room pipeline's minimum door angle and regenerate the room |
| Arms raised / forearms bent forward while standing or walking ("presenting" hands) | the retarget pose is the human's A-pose instead of the reference T-pose | keep `set_tpose_retarget_pose` (log: `retarget pose = reference T-pose …`). Do not re-enable Isaac's auto-posing alone |
| Bones (white ribs, clavicles) visible at the shoulders in arm poses | the humans' rigid `bone_*` anatomy meshes poke through the skin | `isaac.hide_anatomy: true` (default; hides `bone_*` and `teeth_*`) |
| Head tilted back / chest pushed out | spine or neck segments re-aimed in the retarget pose | keep the spine and neck out of `TPOSE_SEGMENTS` (`sdg_xray/rig.py`) |
| Pose looks off (hands too high, low, in front) | `poses.yaml → arm_poses` values | tune `wrist_cm` / `elbow` / `fingers` / `palm` (library frame, cm). Check with `--set isaac.debug_hands=true` and `--set isaac.debug_capture_dir=/tmp/caps` |
| `warning: hands_on_head: wrists … from the pose` | a patient's proportions differ a lot from the library rig, or the pose is beyond reach | as above; the pose clip IK clamps unreachable targets to the arm length |
| Arms swing in opposite directions while going up / down | joint rotations blended the long way round | short-arc blending plus the `via` pose (`poses.yaml`). Keep a `via` for overhead poses |
| Skin visible through the shirt or sleeves in poses | body skin under loose cloth not counted as covered | raise `isaac.clothing_reach_m` (default 0.07). Check that `hide_body_under_clothes` is on and that the log lists the garments |
| Patient dark outside the entrance | the room pipeline lights only the suite | `sequence.outside_light.enabled: true` (default) |
| Odd idle (dancing, tired) | an idle variation from Isaac's default set | `isaac.idle_animation_tags: [Idle]` |
| FOV light invisible or too bright | intensity not calibrated | tune `sequence.fov_light.intensity` / `exposure` once in the GUI |
| `motion library …: not loaded` | no network, or the URL changed | point `isaac.motion_library` at a local copy ([02 §2.4](02_setup.md#24-motion-library-natural-motion)) |
| `2 humans requested but … has only 1 finished` | the latest humans run is partial | `--humans-root` to a complete run, or `--human-ids` |
| SDs `pending` after a crash | Isaac ended before reaching those visits | rerun those humans with `--human-ids`; the new run creates new SDs |

## Checking a run visually (GUI)

1. `.venv/bin/python scripts/run_pipeline.py --humans 1 --keep-open` (or headless with
   `--set isaac.debug_capture_dir=/tmp/caps` and look at the PNGs)
2. Watch the patient walk in, turn on the detector marker, take each pose under the FOV light, and walk out.
3. Compare the console, `timeline.txt` and what you see. The pose events should match the visible poses.
4. Tune the FOV light and the arm poses if needed, then check `--headless` gives the same timeline.
