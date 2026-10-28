# 9. Extending

## 9.1 Spine exams (T and L spine: PA, LLAT, RLAT)

Spine exams only need configuration.

1. Define the projections in `poses.yaml`. Facing and arms can reuse the existing values or new arm poses:

   ```yaml
   projections:
     T_PA:   {facing: detector, arms: hands_on_hip,  label: "Thoracic spine PA"}
     T_LLAT: {facing: right,    arms: hands_on_head, label: "Thoracic spine left lateral"}
     T_RLAT: {facing: left,     arms: hands_on_head, label: "Thoracic spine right lateral"}
     L_PA:   {facing: detector, arms: hands_on_hip,  label: "Lumbar spine PA"}
     L_LLAT: {facing: right,    arms: arms_forward,  label: "Lumbar spine left lateral"}
     L_RLAT: {facing: left,     arms: arms_forward,  label: "Lumbar spine right lateral"}
   ```

2. Add the exam to `run.yaml`:

   ```yaml
   exams:
     CHEST: [PA, LLAT, RLAT]
     SPINE: [T_PA, T_LLAT, T_RLAT, L_PA, L_LLAT, L_RLAT]
   ```

Each human's SD then gets `SPINE/timeline.txt` next to `CHEST/`. Each exam is its own visit (walk in, projections,
walk out). `--exam SPINE` runs only the spine exam.

**Detector height.** The detector and tube are currently set to the patient's T7 height for every exam. For lumbar
projections they should be at about L3. That needs a per-projection (or per-exam) `center_landmark` (e.g. `L3`, which
the humans pipeline provides) and a carriage move between projections. Neither is implemented yet.

## 9.2 A new arm pose

Add an entry to `poses.yaml → arm_poses` in the motion library frame (cm, +X left, +Y up, +Z front). It becomes
the custom action `Xray<PoseName>` automatically. For example, arms forward, holding the stand's side handles:

```yaml
arm_poses:
  arms_forward:
    anchor: Chest
    left: {wrist_cm: [22, 5, 35], elbow: [1, -0.5, 0], fingers: [0, 0, 1], palm: [-1, 0, 0]}
```

Then check it with `--projections <P> --set isaac.debug_hands=true --set isaac.debug_capture_dir=/tmp/caps`
([05 §5.6](05_animation_in_isaac.md#56-arm-poses)).

## 9.3 Other rooms and humans

* **Rooms**: any room from the room pipeline works if its metadata has `anchors.stage.patient_route` (all five steps),
  `detector_normal` and `entrance_door`, and its USD has `Markers/PatientStand` and the collimator `LightWindow`. Rooms
  generated before these fields existed fail with a clear input error.
* **Humans**: any human from the humans pipeline works: Z-Anatomy rig (default) or MPFB rig, picked per human by
  `<id>.json → skeleton.rig` (the retarget maps are checked against real skeletons by a test, and again at run
  time), plus the T7 landmark. Annotations need the Z-Anatomy rig.
* **Another skeleton** (e.g. Mixamo or a Reallusion character): add `configs/retarget_<name>.yaml` (tags,
  `root_joint_name`, axes), add `"retarget_<name>"` to `CONFIG_FILES` in `sdg_xray/paths.py`, and map the rig id to
  it in `isaac.retarget_maps`. The arm poses need no change: they are authored on the motion library rig.

## 9.4 Frame capture (next stage)

The room's D455 exam cameras (`/World/Room/Cameras/RealSense_D455_*`) are already on the stage during each visit. A
capture step can attach Replicator render products to them (see `room/isaac/capture_cameras.py`) and record frames
between the `FOV light ON` and `OFF` events, or for the whole visit. The timeline's `t=` values give the matching
simulation times.

## 9.5 Tests

```bash
.venv/bin/python -m pytest -q tests
```

| Test | Checks |
|---|---|
| `test_default_config_valid`, `test_unknown_projection_rejected` | configuration and validation |
| `test_latest_run_and_selection`, `test_run_dir_given_directly` | run discovery (newest finished run, skipped failed runs), count / ids, errors |
| `test_room_anchors_and_facings` | stage anchors, door facing, entrance facing, left/right turn conventions (RLAT puts the right side on the detector) |
| `test_plan_visit_order` | route order, return to the start point, FOV on exactly `fov_on_s`, arm pose order |
| `test_room_without_route_rejected` | missing anchors give an input error |
| `test_pose_clip_ik_and_annotations` | pose clip IK (wrists at the configured offset, right arm mirrored), frame ranges, ActionStart/Loop/End annotations, BehaviorActionAPI, starts at the idle |
| `test_pose_clip_arms_twist_as_mirror_images` | one idle elbow almost straight: both posed upper arms still twist as mirror images (no wrung shoulder) |
| `test_pose_config_rejected_when_malformed` | arm pose validation |
| `test_sd_numbering_and_timeline` | SD numbering, timeline paths and line format |
| `test_real_inputs_plan` | real latest runs: 2 humans, 1 room, plausible T7 heights, rig + retarget map + 28 annotation points per Z-Anatomy human |
| `test_retarget_map_fits_real_human` | per rig (Z-Anatomy, MPFB): the map chosen by `retarget_maps` names joints of the newest real human with that rig, and they form chains |
| `test_retarget_maps_config` | map selection, default, config errors |
| `test_tag_chain_check_finds_sibling_forearm` | radius beside the ulna is reported; radius under the ulna passes |
| `test_annotation_points_on_real_human` | 24 vertebrae + 2 hips + 2 shoulders; C1 → L5 strictly lower; hip < L5 < shoulder < C1; vertebra point = bone mesh centre; a lift moves every height by the same cm; JSON schema |
| `test_annotations_skip_mpfb_rig` | MPFB-rig humans get no points |
| `test_annotation_projection_and_overlay` | camera projection (image centre, behind the camera), dot at the projected pixel, nothing drawn off-image, frame number |
| `test_annotation_config`, `test_no_overlay_flag` | annotation config validation, `--no-overlay` |
| `test_fov_light_axis_matches_beam` | TubeHead +Y is the room's beam axis |
| `test_compose_into_in_memory` | the room composes into an in-memory stage, detector height set |

The tests do not run Isaac Sim. The animation is checked by running the pipeline ([08](08_troubleshooting.md)).
