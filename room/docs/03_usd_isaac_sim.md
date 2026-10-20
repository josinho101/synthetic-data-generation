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
`sdg:door_facing`, `sdg:entrance_outward_room` and `sdg:placement_origin`. The layer's
`customLayerData.cameraSettings` sets Isaac's perspective viewport (`/OmniverseKit_Persp`) to start
`viewer_distance_m` in front of the door. This only applies when the room file itself is opened. In
a referencing scene, use the `Viewer_Entrance` camera instead.

## 3.2 Prim hierarchy

```
/Room
├── Shell/{Floor, Ceiling, Walls/{South_*, North_*, West_*, East_*}, Doors/Entrance/{JambL, JambR, Head, Leaf}}
├── CheckIn/{Walls, Door, Bench, Hooks/Hook_*, GownShelf/{Board, Gown_*}, Mirror?, Chair?}
├── Equipment/
│   ├── WallStand/{Base, Column, ColumnTrim, TopCap,
│   │             Carriage/{Sleeve, Detector/{Housing, ActiveArea, Handles/{Handle_L, Handle_R, Handle_Top?, Standoff_*}}}}
│   └── TubeStand/{Rail/{Track, EndStop*}, CeilingRail?,
│                 Carriage/{Base, Column, TopGuide?, Arm/{Sleeve, Beam, TubeHead/{Housing, EndCap*,
│                 Collimator/{Body, LightWindow, Knobs, Handle}, FocalSpot}}}}
├── Markers/{Frame/{Outline*, CenterLine, Footprints}, PatientStand, EntranceFrame/{Outline*, Footprints}, EntranceStand}
├── Props/{Table|Stretcher, GeneratorCabinet01, LeadScreen01, ApronRack01/{Apron_*}, Chair01, WasteBin01, StepStool01, CableRun_*}
├── Lights/{Panel_01…, Panel_Changing}/{Frame, Diffuser, RectLight}
├── Cameras/{Cam_FarLeft, Cam_FarRight, Cam_CheckIn, Viewer_Entrance, *_Housing/{Head/{Body, LensRing}, Arm, CeilingPlate}}
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
rp = rep.create.render_product("/Room/Cameras/Cam_FarLeft", (1280, 720))
```

`isaac/capture_cameras.py` does this for every room camera and writes RGB, semantic segmentation and
depth with `BasicWriter` (Script Editor or `./python.sh`; not tested outside Isaac Sim).

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
| required prims (shell, doors, changing room, wall stand + handles + active area, tube stand + rail + head, PatientStand) | error |
| at least one RectLight; every texture file exists | error |
| every mesh has a material | error |
| colliders present (warning when fewer than half the meshes) | error / warning |
| semantic classes floor, wall, wall_detector, detector_handle, xray_tube, floor_marker, door | error |
| world bounds inside footprint + walls; floor top at z = 0 (room frame) | error |
| root placement turns the entrance's outward normal onto `door_facing` | error |
| every camera exists, looks at its target; room / check-in cameras inside the room | error |

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
* `Markers/EntranceStand` is where the patient first stands still just inside the entrance door
  (local −Y points into the room); reference a human there for the "just arrived" pose.
