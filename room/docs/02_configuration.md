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
| `randomize_layout` | false (default): every room has the same layout, and only the appearance changes (see 01 §1.4); true: every room gets its own layout |
| `layout_seed` | which fixed layout (null = `seed`); only used when `randomize_layout` is false |
| `detector_side` | `{left, right}` weights (left = north wall); only used with `equipment.wall_stand.wall: sampled` |
| `changing_room_corner` | `{north, south}`: corner of the check-in room, outside the X-ray room's west wall |
| `entrance_wall` | `{west, side}`: wall of the check-in room with the entrance (outer door from the corridor); `side` = its outer side wall |
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
| `wall_thickness_m` | outer walls of the X-ray room and the check-in room |
| `entrance.width_m`, `height_m`, `open_angle_deg`, `edge_margin_m` | entrance = the check-in room's outer door (swings out into the corridor) |
| `entrance.min_width_m` | a sampled entrance wider than the check-in room wall allows is narrowed, down to this |
| `changing_room.length_m`, `depth_m` | check-in room interior size ranges (it is built outside the footprint, at x < 0) |
| `changing_room.door_width_m`, `door_height_m`, `door_open_angle_deg` | connecting door check-in room → X-ray room (swings into the X-ray room) |
| `changing_room.bench_depth_m`, `bench_height_m`, `p_mirror`, `p_chair` | furniture |
| `walk.agent_radius_m`, `grid_m`, `door_clearance_m` | walk-path checks (entrance → connecting door; connecting door → marker) |

## equipment.yaml

| Key | Meaning |
|---|---|
| `wall_stand.wall` | `opposite_checkin` (default): detector on the long wall away from the check-in room / connecting door; `sampled`: by `variations.detector_side` |
| `wall_stand.placement` | `far_end` (default): as far from the connecting door as the tripods allow; `random`: sampled along the wall |
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
| `equipment` | body / accent colours (body: light greys, a shade darker than white walls), chrome roughness, detector front colour |
| `equipment.min_wall_delta_e` | minimum CIELAB ΔE between the equipment body and the wall colour (default 10); a closer body colour is darkened, so the equipment stays visible under white / camera light. `<id>.json → equipment.finish.body_color_sampled` = before correction |

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

### Exam cameras (Intel RealSense D455) — `sensors` and `exam_cameras`

RGB-D cameras around the exam position, for capturing the patient's X-ray poses later. Every number
may be fixed or `[min, max]` (sampled per room). Every `exam_cameras.defaults` key can be overridden
per camera. The top-level `enabled: false` also switches them off.

| Key | Meaning |
|---|---|
| `sensors.d455.depth.fov_deg`, `resolution`, `range_m`, `offset_m` | depth stream (datasheet 87° × 58°, 1280 × 720, 0.6–6 m); origin = left imager |
| `sensors.d455.color.fov_deg`, `resolution`, `offset_m` | colour stream (90° × 65°, 1280 × 800), offset [right, up, forward] in the camera frame (approximate: use calibrated extrinsics when known) |
| `sensors.d455.baseline_m`, `body_size_m` | stereo baseline, camera body [width, depth, height] |
| `sensors.d455.horizontal_aperture_mm`, `clipping_range_m` | USD optics: focal = aperture / (2 tan(FOV_h / 2)), vertical aperture from FOV_v |
| `sensors.d455.asset` | optional USD for the camera body (e.g. Isaac Sim `…/Sensors/Intel/RealSense/rsd455.usd`; frame: +X = view direction, Z up, meters) |
| `exam_cameras.enabled` | false = no exam cameras (and no tripods) |
| `exam_cameras.defaults.rig` | key of `sensors` (add another RGB-D model as a sibling of `d455`) |
| `exam_cameras.defaults.streams` | `[color, depth]`; drop one to write a single camera |
| `exam_cameras.defaults.orientation` | `landscape` or `portrait` (upright camera, tall image: FOV and resolution swapped; body drawn on its side). Defaults: Front / Left / Right portrait, Top landscape |
| `exam_cameras.defaults.position_jitter_m`, `target_jitter_m` | per-room random offsets (0 keeps the 1.4 m / 1.0 m exact) |
| `exam_cameras.defaults.stand` | draw the stand / bracket meshes |
| `exam_cameras.defaults.movement_margin_m`, `body_height_m` | patient movement zone: marker outline grown by the margin, floor to body height |
| `exam_cameras.lateral_search.angle_step_deg`, `max_swing_deg`, `footprint_m` | tripod swing around the detector centre when the side-on spot is blocked; tripod leg spread |
| `exam_cameras.min_movement_coverage` | warn when a camera frames less of the movement zone |
| `cameras.<name>.mount` | `detector_lateral_left` / `detector_lateral_right` (tripod), `tube_head` (bracket), `detector_top` (post + arm) or `[x, y, z]` |
| `cameras.<name>.radius_m`, `height_m` | lateral: horizontal distance from the detector centre (1.4), lens height (1.0) |
| `cameras.<name>.offset_m` | tube_head: [along the rail, along the beam, up] from the focal spot (default [0, 0.20, 0.16]: centred on the beam line, above the front of the collimator) |
| `cameras.<name>.tilt_deg` | optional: look at the target's x, y but pitched this much below horizontal (Front: 10) |
| `cameras.<name>.min_movement_coverage` | per-camera override of `exam_cameras.min_movement_coverage` (Front: 0.6) |
| `cameras.<name>.extension_m`, `rise_m` | detector_top: arm reach out from the detector face (0.2), post height above the housing top (0.1) |
| `cameras.<name>.target` | `patient_side` (movement-zone centre, mid-body), `patient_top` (movement-zone floor centre), any room-camera target, or `[x, y, z]` |
| `cameras.<name>.stand_type` | `tripod`, `bracket`, `post_arm`, `none` |

Examples:

```bash
--set cameras.exam_cameras.cameras.RealSense_D455_Left.radius_m=1.6                 # tripod further away
--set cameras.exam_cameras.cameras.RealSense_D455_Left.height_m=[0.9,1.2]           # sampled lens height
--set cameras.exam_cameras.cameras.RealSense_D455_Right.orientation=landscape
--set cameras.exam_cameras.cameras.RealSense_D455_Top.extension_m=0.3
--set cameras.exam_cameras.cameras.RealSense_D455_Front.enabled=false
--set cameras.exam_cameras.defaults.streams=[depth]                       # depth cameras only
--set cameras.exam_cameras.enabled=false                                  # no exam cameras / tripods
```

## export.yaml

| Key | Meaning |
|---|---|
| `output_root`, `run_dir_format` | where runs go |
| `workers`, `retries` | parallel build processes, retries per failed room |
| `usd.file_format` | `usd` (binary crate) or `usda` (text) |
| `usd.root_prim`, `cylinder_segments` | default prim, cylinder tessellation |
| `placement.door_facing` | stage direction the entrance's outside (the check-in room's outer door) faces: −Y (default, towards the viewer), +Y, −X, +X |
| `placement.origin` | `center` (X-ray room footprint centre at 0,0), `entrance_door`, `room_corner` (room frame = stage frame when the entrance is on the west wall and door_facing is −X) |
| `placement.set_viewport_camera`, `viewer_distance_m`, `viewer_height_m` | Isaac viewport start view in front of the door (`customLayerData.cameraSettings`) and the Viewer_Entrance camera |
| `physics.colliders`, `approximation` | `CollisionAPI` + `MeshCollisionAPI` approximation on all solid meshes |
| `physics.props_rigid_body` | props become dynamic rigid bodies |
| `semantics` | write class labels |
| `preview.plan_px_per_m`, `contact_sheet_columns` | floor plan PNG / contact sheet |


## Corridor (`room.yaml → corridor`)

| Key | Default | Meaning |
|---|---|---|
| `enabled` | true | build the corridor outside the entrance |
| `depth_m` / `width_m` | 3.0 / 2.4 | floor rectangle: out from the wall's outer face / along the wall, centred on the entrance door |
| `light.enabled` | true | ceiling-height RectLight panel above the corridor (emits down, same colour temperature as the room) |
| `light.size_m` / `height_m` | [1.2192, 0.6096] / 2.6 | panel size and height |
| `light.relative_to_exam_panels` | 1.0 | luminance relative to the X-ray room's ceiling panels |

The rectangle is stored on the root as `sdg:corridor_block` (room frame), and the validation allows geometry there.

## FOV light (`equipment.yaml → tube_stand.fov_light`)

| Key | Default | Meaning |
|---|---|---|
| `enabled` | true | build `Collimator/FOVLight` |
| `field_cm` | [35, 43] | lit field [width, height] at the room's SID; the IES half-angles are `atan(field / 2 / SID)` |
| `intensity` | 150000 | DiskLight intensity (nits): a clearly visible field over the room light |
| `radius_m`, `color`, `edge_deg`, `offset_m` | 0.01, warm white, 0.4°, 0.03 m | emitter size, colour, soft edge of the field, distance in front of the collimator |

RTX's spotlight cone on area lights produces only a few-centimetre spot, so the field shape comes from the IES profile
(LM-63, type C; intensity only inside the rectangle). The light is created invisible (`visibility = invisible`,
`sdg:role = fov_light`, `sdg:field_cm`, `sdg:sid_m`).

## TOP exam camera height (`cameras.yaml → RealSense_D455_Top.rise_m`)

The post on top of the detector is 0.80 m (it was 0.10 m). The camera moves with the detector, which is set to the
patient's chest height, so a short post put the lens level with the patient's head: raised arms hit it and the view was
blocked. With 0.80 m the lens is about 2.3–2.4 m high and at least 0.6 m (the D455 minimum depth) above the tallest
patient's head; the arm still reaches 0.2 m out from the detector face.
