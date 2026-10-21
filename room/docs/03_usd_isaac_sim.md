# 3. USD structure & Isaac Sim

## 3.1 Stage

`metersPerUnit = 1`, `upAxis = Z`, defaultPrim `/Room` (kind `assembly`). The root carries
`sdg:room_id`, `sdg:seed`, `sdg:generator_version` and `sdg:footprint_m` (length, width, ceiling).
All geometry is `UsdGeom.Mesh` (`subdivisionScheme = none`, faceVarying normals and `st` UVs).
Materials are `UsdPreviewSurface`, which RTX renders directly. Textures are referenced as
`./textures/<file>.png`.

### Placement

`/Room` has `xformOp:translate` + `xformOp:rotateZ` so that, on the stage, the footprint centre is at
(0, 0, 0), the floor at z = 0, and the entrance's outside faces `export.placement.door_facing`
(default −Y). This holds whichever wall the entrance was sampled on. The root also carries
`sdg:door_facing`, `sdg:entrance_outward_room`, `sdg:placement_origin`, and the extents of the
check-in room and the outward entrance swing outside the footprint (`sdg:checkin_block`,
`sdg:entrance_swing`, room frame [x0, y0, x1, y1]). The layer's
`customLayerData.cameraSettings` sets Isaac's perspective viewport (`/OmniverseKit_Persp`) to start
`viewer_distance_m` in front of the door. This only applies when the room file itself is opened. In
a referencing scene, use the `Viewer_Entrance` camera instead.

## 3.2 Prim hierarchy

```
/Room
├── Shell/{Floor, Ceiling, Walls/{South_*, North_*, West_* (connecting-door opening), East_*},
│          Doors/Entrance/{JambL, JambR, Head, Leaf}}            entrance = the check-in room's outer door
├── CheckIn/{Floor, Ceiling, Walls/{West_*, Outer_*, Inner_*}, Door (connecting door), Bench, Hooks/Hook_*,
│           GownShelf/{Board, Gown_*}, Mirror?, Chair?}           outside the footprint (x < 0)
├── Equipment/
│   ├── WallStand/{Base, Column, ColumnTrim, TopCap,
│   │             Carriage/{Sleeve, Detector/{Housing, ActiveArea, Handles/{Handle_L, Handle_R, Handle_Top?, Standoff_*}}}}
│   └── TubeStand/{Rail/{Track, EndStop*}, CeilingRail?,
│                 Carriage/{Base, Column, TopGuide?, Arm/{Sleeve, Beam, TubeHead/{Housing, EndCap*,
│                 Collimator/{Body, LightWindow, Knobs, Handle, FOVLight}, FocalSpot}}}}
├── Corridor/{Floor/FloorSlab, Light/RectLight}                     outside the entrance (room.yaml corridor)
├── Markers/{Frame/{Outline*, CenterLine, Footprints}, PatientStand, EntranceFrame/{Outline*, Footprints}, EntranceStand}
├── Props/{Table|Stretcher, GeneratorCabinet01, LeadScreen01, ApronRack01/{Apron_*}, Chair01, WasteBin01, StepStool01, CableRun_*}
├── Lights/{Panel_01…, Panel_Changing}/{Frame, Diffuser, RectLight}
├── Cameras/{CeilingCam_FarLeft, CeilingCam_FarRight, CeilingCam_CheckIn, Viewer_Entrance, *_Housing/{Head/{Body, LensRing}, Arm, CeilingPlate},
│            RealSense_D455_<Front|Left|Right|Top>/{RealSense_D455_<…>_RGB, RealSense_D455_<…>_Depth},
│            RealSense_D455_<…>_Mount/{Head/{Body, Lens0, Lens1}, Column, Plate, Hub, Leg0-2 | Post, Foot, Arm, Hanger}}
└── Looks/  Floor, Wall, Ceiling, EquipBody, EquipAccent, Metal, DetectorFront, Tape, Footprints, DoorLeaf, …
```

### Moving parts

| Prim | Op | Meaning | Limits |
|---|---|---|---|
| `WallStand/Carriage` | translate z | detector centre height | `sdg:travel_min/max` |
| `TubeStand/Carriage` | translate x (stand frame) | position along the rail | `sdg:travel_min/max` |
| `TubeStand/Carriage/Arm` | translate z | tube centre height | `sdg:travel_min/max` |
| `…/Arm/TubeHead` | (add rotate) | focal spot, +Y = beam direction | |

Example in the Isaac Script Editor:

```python
from pxr import UsdGeom, Gf
import omni.usd
stage = omni.usd.get_context().get_stage()
op = UsdGeom.Xformable(stage.GetPrimAtPath("/World/Room/Equipment/WallStand/Carriage")).GetOrderedXformOps()[0]
op.Set(Gf.Vec3d(0, 0, 1.45))      # detector centre to 1.45 m
```

### Cameras

`UsdGeom.Camera` (perspective) with one `xformOp:transform` (look-at: −Z towards `sdg:target`, +Y up),
`focalLength` / `horizontalAperture` / `verticalAperture` in mm and `clippingRange`. Custom
attributes are `sdg:resolution` (int2), `sdg:target` (room frame), `sdg:mount` and `sdg:fov_h_deg`. Select
them in the viewport camera menu, or use them for Replicator render products:

```python
import omni.replicator.core as rep
rp = rep.create.render_product("/Room/Cameras/CeilingCam_FarLeft", (1280, 720))
```

`isaac/capture_cameras.py` does this for every room camera and writes RGB, semantic segmentation and
depth with `BasicWriter` (Script Editor or `./python.sh`; not tested outside Isaac Sim).

### Exam cameras (Intel RealSense D455)

Each exam camera is an `Xform` `/Room/Cameras/RealSense_D455_<Front|Left|Right|Top>` carrying the look-at
transform (camera frame: +X right, +Y up, −Z view). Left / right are the patient's left / right while facing the
detector; Front is the camera on the X-ray source. Each rig has one `UsdGeom.Camera` per stream, with a unique
name so Isaac's viewport camera menu shows which camera it is:

| Prim | Optics (h × v) landscape / portrait | Resolution landscape / portrait | Offset in the rig |
|---|---|---|---|
| `RealSense_D455_<…>_Depth` | 87° × 58° / 58° × 87° | 1280 × 720 / 720 × 1280 | origin (left imager) |
| `RealSense_D455_<…>_RGB` | 90° × 65° / 65° × 90° | 1280 × 800 / 800 × 1280 | `sensors.d455.color.offset_m` (≈ 5.9 cm, approximate) |

Front, Left and Right are **portrait**: the camera prim stays upright and the image is tall (the D455 body is
drawn on its side, as it would be mounted). Top is **landscape** and looks down; its image width runs along
the detector wall and the image top points away from the detector. Every camera aims at the patient on the floor
marker and has `focusDistance` = the distance to that point, with `fStop` = 0 (no depth-of-field blur).

Rig attributes: `sdg:rig` (`d455`), `sdg:mount`, `sdg:attached_to` (`floor` / `tube_head` /
`wall_stand_carriage`), `sdg:orientation`, `sdg:target`, `sdg:depth_range_m`. Stream attributes:
`sdg:stream`, `sdg:resolution`, `sdg:fov_h_deg`, `sdg:fov_v_deg`.

**The big grey movie-camera shapes in the Isaac viewport are not the cameras' geometry.** Isaac draws an icon
at every camera prim, and each D455 has two (RGB + Depth). The icons don't appear in renders or captures. Hide
them with the viewport eye menu → *Show By Type → Cameras*; the real-size D455 bodies (124 × 29 × 26 mm),
tripods and brackets are then visible.

The hardware is under `RealSense_D455_<…>_Mount` (label `camera_stand`; the body is labelled `rgbd_camera`):

| Camera | Mount | Hardware |
|---|---|---|
| `RealSense_D455_Left` / `RealSense_D455_Right` | floor, 1.4 m from the detector centre, lens 1.0 m | tripod: 3 legs + centre column (legs and column have colliders) |
| `RealSense_D455_Front` | top of the tube housing | bracket post (no collider) |
| `RealSense_D455_Top` | detector housing top | post + arm reaching 0.2 m out from the detector face (no collider) |

The cameras are fixed prims (not children of the equipment). `isaac/compose_scene.py` shifts
`RealSense_D455_Top` / `RealSense_D455_Front` together with the detector / tube when it sets their height. If you move
the carriage yourself, move the rigs with `sdg:attached_to` by the same amount. A body asset can
replace the primitive body: `sensors.d455.asset` (e.g. Isaac Sim's `rsd455.usd`), referenced at
`RealSense_D455_<…>_Mount/Head/Body`.

## 3.3 Physics and semantics

* `UsdPhysics.CollisionAPI` + `MeshCollisionAPI` (`convexHull`) on every solid mesh (static
  colliders). Decals, door handles, hooks, light frames and cable posts have no collider.
  `export.physics.props_rigid_body: true` makes props dynamic (`RigidBodyAPI`).
* Class labels are written in both Isaac formats: `SemanticsAPI:Semantics`
  (`semantic:Semantics:params:semanticData`) and `SemanticsLabelsAPI:class`
  (`semantics:labels:class`). Classes include: `floor, ceiling, wall, door, bench, coat_hook, shelf,
  gown, mirror, wall_stand, wall_detector, detector_active_area, detector_handle, xray_tube_stand,
  tube_rail, xray_tube, collimator, floor_marker, light_panel, chair, lead_apron, lead_screen, cabinet,
  waste_bin, step_stool, table, stretcher, cable`. The full prim → label map is in `<id>.json → semantic_labels`.

## 3.4 Validation (`scripts/validate_usd.py`, also after every build)

| Check | Level |
|---|---|
| stage opens; Z-up; metersPerUnit 1; defaultPrim | error |
| required prims (shell, doors, check-in room, wall stand + handles + active area, tube stand + rail + head, PatientStand) | error |
| at least one RectLight; every texture file exists | error |
| every mesh has a material | error |
| colliders present (warning when fewer than half the meshes, camera hardware not counted) | error / warning |
| semantic classes floor, wall, wall_detector, detector_handle, xray_tube, floor_marker, door | error |
| world bounds inside footprint + walls + check-in room + outward entrance swing; floor top at z = 0 (room frame) | error |
| root placement turns the entrance's outward normal onto `door_facing` | error |
| every camera (and every RGB / Depth stream of an exam camera) exists, looks at its target; room and exam cameras inside the X-ray room, the check-in camera inside the check-in room | error |

Parts replaced by an `asset:` override skip their procedural-only checks.

## 3.5 Lights and lux calibration

Each panel is a `UsdLux.RectLight` (`normalize = false`, `exposure = 0`, `enableColorTemperature`,
`colorTemperature = K`) 17 mm below the ceiling, emitting down. A slightly emissive diffuser mesh
only gives the panel its look. `photometry.py` integrates the direct illuminance of all exam panels
over a 20 cm floor grid and solves the panel luminance `L` (written as `intensity`, in nits per the
UsdLux convention) so that

    mean(E_direct) × indirect_gain × lux_calibration = target lux

`<id>.json → lighting.photometry` lists target, direct mean/min/max, estimated total and uniformity.

<a id="lux-calibration"></a>**One-time calibration in Isaac Sim.** Render a room under its lights
with auto-exposure off. Measure the floor illuminance at the marker, either with a light meter
approach (render a known-albedo grey card and convert pixel radiance) or from the RTX light
statistics. Then set

    lux_calibration = (lux measured in Isaac) / (estimated_lux_mean in <id>.json)

in `configs/lighting.yaml` and regenerate. From then on new rooms hit the target in Isaac.

## 3.6 Importing

* *File → Open* `R0001.usd`, or reference it: `prim.GetReferences().AddReference(".../R0001.usd")`.
  Keep the folder intact.
* The room is centred at the origin with the door facing −Y; translate / rotate the referencing prim to move it.
* Synthetic humans: reference them onto `Markers/PatientStand` (local −Y points at the detector,
  as the humans face −Y), or use `isaac/compose_scene.py`.
* `Markers/EntranceStand` is where the patient first stands still just inside the X-ray room, past the
  connecting door from the check-in room (local −Y points into the room). Reference a human there for
  the "just arrived" pose. `<id>.json → anchors.patient_route` lists the whole route: entrance →
  check-in room → connecting door → entrance stand → patient stand.
