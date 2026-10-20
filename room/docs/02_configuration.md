# 2. Configuration reference

All files are in `configs/`. Any value can be overridden on the command line with
`--set <file>.<key>[.<key>…]=<YAML value>`, e.g. `--set room.footprint_ft=[20,10]` or
`--set lighting.lux.mean=300`. The configuration is validated before a run (`config/schema.py`).
Errors list the offending key.

## variations.yaml

| Key | Meaning |
|---|---|
| `count`, `seed`, `id_prefix`, `id_digits` | number of rooms, global seed, ids `R0001…` |
| `max_layout_attempts` | resamples per room before the run fails |
| `detector_side` | `{left, right}` weights (left = north wall) |
| `changing_room_corner` | `{north, south}` |
| `entrance_wall` | `{west, long_wall}` |
| `changing_door_wall` | `{east, inner}` |
| `wall_finish` | keys of `materials.walls` (white / beige / gray / tiled) |
| `floor_material` | keys of `materials.floors` (vinyl / tile / concrete) |
| `cct_class` | keys of `lighting.cct_k` (warm / neutral / cool) |
| `patient_support` | `{none, table, stretcher}` |
| `tube_column_type` | `{floor, floor_ceiling}` |

Weights are relative (they do not need to sum to 100). Set a weight to 0 to switch an option off.

## room.yaml

| Key | Meaning |
|---|---|
| `footprint_ft` / `footprint_m` | [length, width] clear interior; `footprint_m` wins when set; length ≥ width |
| `ceiling_height_m` | room height: a number (fixed) or [min, max] (sampled); CLI `--height <m>` |
| `ceiling_height_ft` | same in feet; wins when set (null = use meters) |
| `wall_thickness_m`, `partition_thickness_m` | outer walls / changing-room walls |
| `entrance.width_m`, `height_m`, `open_angle_deg`, `edge_margin_m`, `long_wall_max_x_m` | entrance door |
| `changing_room.length_m`, `depth_m` | changing-room interior size ranges |
| `changing_room.door_width_m`, `door_height_m`, `door_open_angle_deg` | its door |
| `changing_room.bench_depth_m`, `bench_height_m`, `p_mirror`, `p_chair` | furniture |
| `walk.agent_radius_m`, `grid_m`, `door_clearance_m` | walk-path check |

## equipment.yaml

| Key | Meaning |
|---|---|
| `wall_stand.asset` | external USD for the whole wall stand (origin at the wall, +Y into the room) |
| `wall_stand.column_size_m`, `column_height_m`, `base_size_m`, `wall_gap_m` | stand geometry |
| `wall_stand.carriage_travel_m` | detector centre height limits (written as `sdg:travel_min/max`) |
| `wall_stand.detector_center_height_m` | sampled detector centre height for the room |
| `detector.housing_size_m`, `active_area_m`, `aec_chambers` | flat panel housing + front marking |
| `handles.side`, `side_length_m`, `bar_radius_m`, `standoff_m`, `p_top_bar` | patient grips |
| `tube_stand.asset` | external USD for the tube stand (origin at the rail centre on the wall, +Y towards the detector) |
| `tube_stand.rail_*`, `column_*`, `carriage_size_m`, `arm_*`, `housing_*`, `collimator_size_m` | tube stand geometry |
| `tube_stand.sid_m` | SID range (clipped to the room width; schema error if the minimum cannot fit) |
| `beam_corridor_half_width_m` | half width of the keep-out band between tube and detector |
| `floor_marker.*` | stand gap, outline size, tape width / colours, footprint spacing, centre line |
| `floor_marker.min_floor_delta_e` | the sampled tape colour is darkened until its CIELAB ΔE to the floor colour reaches this (default 30), so the markers are always easy to see |
| `entrance_marker.enabled`, `distance_from_door_m` | marker where the patient first stands still just inside the entrance door (same tape and footprints, no centre line) |

## materials.yaml

| Key | Meaning |
|---|---|
| `texture_resolution` | PNG size of the procedural textures |
| `walls.<finish>` | colours, roughness range; `tiled` also tile sizes and grout colours |
| `color_jitter` | HSV jitter amplitude applied per room |
| `min_floor_wall_delta_e` | minimum CIELAB ΔE between floor and wall colour (default 10); a closer floor is darkened (or lightened). `<id>.json → room.floor.delta_e_to_wall`, `color_sampled` = before correction |
| `floors.<type>` | colours, roughness, vinyl speckle, tile sizes / grout, texture repeat size |
| `ceiling` | acoustic tile colour, 2 ft grid, T-bar colour |
| `doors` | leaf colours, frame colour |
| `glare`, `glare_levels` | none / mild / strong → roughness and clearcoat ranges of the equipment paint |
| `equipment` | body / accent colours, chrome roughness, detector front colour |

## lighting.yaml

| Key | Meaning |
|---|---|
| `lux.mean/sd/min/max` | truncated normal of the exam-room floor illuminance (lux) |
| `cct_k.<class>` | K range per colour-temperature class |
| `panels.sizes_m`, `size_weights`, `count_exam`, `count_changing`, `changing_lux`, `diffuser_emissive` | ceiling panels |
| `indirect_gain` | estimated (direct + bounced) / direct ratio |
| `lux_calibration` | Isaac-measured / predicted lux, see 03 §3.5 |
| `workplane_height_m`, `grid_m` | illuminance grid |
| `ambient_dome` | DomeLight intensity (0 = none) |

## props.yaml

`items.<name>`: `p` (probability) or `count: [min, max]`, `size_m: [x, y, height]` (local x along the
wall for wall items), `wall: true/false`, `colors`. `apron_rack.aprons` is the apron count range.
`cable_runs.count` controls the floor cover (1) and the wall conduit (2).
`patient_support.<table|stretcher>` gives size, `alternatives` (smaller sizes tried when the first
does not fit), frame and pad colours. `changing_room` gives hook count, shelf size, gown and bench
colours. `clearance_m` is the gap between items.

## cameras.yaml

| Key | Meaning |
|---|---|
| `enabled` | false = no cameras at all |
| `defaults.*` | applied to every camera unless the camera sets the key |
| `focal_length_mm` | number or [min, max] (sampled); FOV_h = 2·atan(aperture / 2f) |
| `horizontal_aperture_mm` | sensor width; vertical aperture follows the resolution aspect |
| `clipping_range_m`, `resolution` | near/far clip; [width, height] px (`sdg:resolution`, used for render products) |
| `ceiling_gap_m`, `corner_inset_m`, `wall_offset_m` | mount offsets (lens below ceiling, from the side wall, from the mount wall) |
| `position_jitter_m`, `target_jitter_m` | per-room random offsets |
| `housing` | small camera body + ceiling arm (no collider, label `security_camera`) |
| `obstacle_clearance_m`, `max_slide_m` | a far-wall camera closer than this to tall equipment (≥ 1.4 m: stands, cabinet, lead screen, apron rack) slides along the wall towards the other corner, by at most `max_slide_m` |
| `coverage.focal_length_mm`, `margin` | lens range and frame margin for auto-framed cameras |
| `coverage.search_step_m`, `search_fraction` | mount positions tried along the far wall (from the corner) |
| `coverage.weights`, `required`, `enforce` | score weights per group (marker, walk_path = hips + head, walk_feet, support, room); minimum union coverage; resample rooms below it |
| `coverage.marker_heights_m`, `walk_heights_m`, `feet_height_m`, `walk_spacing_m`, `room_grid_m`, `occlusion` | sample points and occlusion test |
| `cameras.<name>.auto_frame` | true: position / aim / lens solved for coverage (far-wall cameras); false: use `target`, `focal_length_mm`, jitter |
| `cameras.<name>.enabled/mount/target` | `mount`: far_wall_left, far_wall_right, checkin_corner, entrance_outside or [x,y,z] (room frame); `target`: room_center, floor_marker, detector, checkin_center, checkin_door, entrance_door or [x,y,z] |

Add a camera by adding a new `cameras.<name>` entry. Disable one with `--set cameras.cameras.<name>.enabled=false`.

## export.yaml

| Key | Meaning |
|---|---|
| `output_root`, `run_dir_format` | where runs go |
| `workers`, `retries` | parallel build processes, retries per failed room |
| `usd.file_format` | `usd` (binary crate) or `usda` (text) |
| `usd.root_prim`, `cylinder_segments` | default prim, cylinder tessellation |
| `placement.door_facing` | stage direction the entrance's outside faces: −Y (default, towards the viewer), +Y, −X, +X |
| `placement.origin` | `center` (footprint centre at 0,0), `entrance_door`, `room_corner` (room frame = stage frame when the entrance is on the west wall and door_facing is −X) |
| `placement.set_viewport_camera`, `viewer_distance_m`, `viewer_height_m` | Isaac viewport start view in front of the door (`customLayerData.cameraSettings`) and the Viewer_Entrance camera |
| `physics.colliders`, `approximation` | `CollisionAPI` + `MeshCollisionAPI` approximation on all solid meshes |
| `physics.props_rigid_body` | props become dynamic rigid bodies |
| `semantics` | write class labels |
| `preview.plan_px_per_m`, `contact_sheet_columns` | floor plan PNG / contact sheet |
