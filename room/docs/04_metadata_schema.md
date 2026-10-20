# 4. Metadata schema

## 4.1 `<id>.json` (one per room)

| Field | Content |
|---|---|
| `id`, `run_id`, `generator_version`, `created_utc`, `seed`, `attempt`, `layout_rejections` | identity; `attempt` = how often the layout was resampled, with the reasons |
| `usd`, `units`, `coordinate_frame` | file name, meters / Z-up, frame description |
| `placement` | door_facing, origin, yaw_deg, translate_m (room frame → stage) |
| `room.footprint_m`, `ceiling_height_m` | size |
| `room.wall_finish` | finish, colour, roughness (+ tile size, grout for tiled) |
| `room.floor` | material, colour, roughness, texture seed, tile size / speckle |
| `lighting` | CCT class + K, panel size, panel list (centre, size, zone), `photometry.exam/changing` (luminance nits, target, direct and estimated lux mean/min/max, uniformity) |
| `equipment` | detector side, finish (colours, roughness, clearcoat), wall stand (origin, yaw, footprint, heights, top bar), detector (centre, normal, face offset), tube stand (rail, carriage, arm, focal offset, column type), focal spot, beam axis, SID, beam corridor |
| `anchors.patient_stand` | position, yaw, facing, prim path |
| `anchors.entrance_stand` | entrance marker (just inside the connecting door): position, yaw, facing (into the room), prim path; `null` when disabled |
| `anchors.detector_center/normal`, `focal_spot`, `beam_axis`, `sid_m` | imaging geometry in room coordinates |
| `anchors.entrance_door`, `changing_door`, `changing_room_inside`, `checkin_start` | patient-flow points: entrance (check-in room's outer door), connecting door, inside the check-in room, just inside the entrance |
| `anchors.patient_route` | ordered route `[{step, position}]`: `entrance` → `check_in` → `connecting_door` → `entrance_stand` → `patient_stand` (room frame) |
| `anchors.stage.*` | patient stand (+ yaw), detector centre / normal, focal spot, beam axis, doors, `patient_route` on the Isaac stage |
| `camera_coverage` | fraction of sample points seen by at least one X-ray-room camera: marker, walk_path (hips + head), walk_feet, support, room; plus point counts |
| `cameras[]` | name, prim, mount, zone, auto_frame, coverage (per camera), position / target (room) and `position_stage` / `target_stage`, focal length, apertures, FOV h/v, resolution, clipping range, housing |
| `cameras[]` (exam cameras, `rig` set) | additionally: `rig` (`d455`), `zone: exam`, `attached_to` (`floor` / `tube_head` / `wall_stand_carriage`), `orientation`, `up` / `up_stage`, `streams.{color,depth}` (focal, apertures, FOV, resolution, offset, range), `stream_prims` (`<rig>/<rig>_RGB`, `<rig>/<rig>_Depth`), `focus_distance_m`, `depth_range_m`, `baseline_m`, `stand`, `stand_type`, `mount_info` (tripod rect + swing, bracket base, arm extension / rise), `movement_coverage` (`body`, `floor` fractions of the movement zone in frame), `min_patient_distance_m`, `within_depth_range`, `radius_m` / `height_m` (tripods). The main optics fields are those of the depth stream (portrait: FOV and resolution already swapped) |
| `changing_room` | check-in room (outside the X-ray room, x < 0): corner, `location`, interior, block (incl. walls), connecting door (wall, centre, width, plane, hinge, angle, swing), bench, hooks, shelf, mirror, chair |
| `entrance` | the check-in room's outer door: wall, centre, width (`width_sampled_m` before narrowing), height, plane, `out_normal`, hinge, open angle, swing zone (outside, `swings: out`), `placed_on` (`west` / `side`) |
| `layout.exam_cameras` (in `manifest.json`) | tripod spots: position, radius, height, angle, swing, stand rect |
| `patient_support` | table / stretcher with rect, yaw, size, colours, or null |
| `props`, `props_requested`, `props_dropped` | placed items (rect, yaw, size, colour), requested names, dropped names |
| `cable_runs` | floor covers (polyline) and wall conduits (rect) |
| `prims` | USD paths of the key parts (wall stand, carriage, detector, handles, tube head, focal spot, marker, lights, props) |
| `semantic_labels` | prim path → class label |
| `textures` | generated texture files |
| `layout_notes`, `warnings` | solver notes (e.g. entrance on the other check-in wall or narrowed, tripod swung, items dropped, top camera closer than the D455 minimum depth) and warnings (e.g. low camera coverage) |
| `validation` | result of 03 §3.4 (status, errors, warnings, bounds, mesh and light counts) |

## 4.2 Run files

| File | Content |
|---|---|
| `manifest.json` | `{meta, rooms: [spec + layout]}`, the input for `--resume` / `--only` |
| `results.json` | per room: status, usd, warnings, validation, estimated lux, duration, log |
| `rooms.csv` | one row per room: categorical choices, sizes, CCT, lux, SID, detector height/x, support, props |
| `summary.json` | status counts, failed ids, configured vs achieved distributions, lux stats, dropped props, rejections, timings |
| `contact_sheet.png` | all floor plans |
