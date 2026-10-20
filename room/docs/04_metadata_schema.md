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
| `anchors.entrance_stand` | entrance marker: position, yaw, facing (into the room), prim path; `null` when disabled |
| `anchors.detector_center/normal`, `focal_spot`, `beam_axis`, `sid_m` | imaging geometry in room coordinates |
| `anchors.entrance_door`, `changing_door`, `changing_room_inside` | patient-flow points |
| `anchors.stage.*` | patient stand (+ yaw), detector centre / normal, focal spot, beam axis, doors on the Isaac stage |
| `camera_coverage` | fraction of sample points seen by at least one X-ray-room camera: marker, walk_path (hips + head), walk_feet, support, room; plus point counts |
| `cameras[]` | name, prim, mount, zone, auto_frame, coverage (per camera), position / target (room) and `position_stage` / `target_stage`, focal length, apertures, FOV h/v, resolution, clipping range, housing |
| `changing_room` | interior, partitions, door (wall, centre, width, hinge, angle, swing), bench, hooks, shelf, mirror, chair |
| `entrance` | wall, centre, width, height, hinge, open angle, swing zone, `placed_on` |
| `patient_support` | table / stretcher with rect, yaw, size, colours, or null |
| `props`, `props_requested`, `props_dropped` | placed items (rect, yaw, size, colour), requested names, dropped names |
| `cable_runs` | floor covers (polyline) and wall conduits (rect) |
| `prims` | USD paths of the key parts (wall stand, carriage, detector, handles, tube head, focal spot, marker, lights, props) |
| `semantic_labels` | prim path → class label |
| `textures` | generated texture files |
| `layout_notes`, `warnings` | solver notes (e.g. entrance moved to the long wall, items dropped) |
| `validation` | result of 03 §3.4 (status, errors, warnings, bounds, mesh and light counts) |

## 4.2 Run files

| File | Content |
|---|---|
| `manifest.json` | `{meta, rooms: [spec + layout]}`, the input for `--resume` / `--only` |
| `results.json` | per room: status, usd, warnings, validation, estimated lux, duration, log |
| `rooms.csv` | one row per room: categorical choices, sizes, CCT, lux, SID, detector height/x, support, props |
| `summary.json` | status counts, failed ids, configured vs achieved distributions, lux stats, dropped props, rejections, timings |
| `contact_sheet.png` | all floor plans |
