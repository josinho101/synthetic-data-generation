# 1. Overview, coordinate frame & layout rules

## 1.1 Pipeline

| Stage | Code | What happens | Output |
|---|---|---|---|
| preflight | `pipeline/orchestrator.py:preflight` | Python, packages, output folder, disk, asset paths | `preflight.json` |
| sample | `sampling/sampler.py` | seed → every random choice of a room (finishes, light, SID, heights, props wanted) | spec |
| layout | `layout/solver.py` | spec → floor positions; unsolvable → resample (`attempt + 1`) | `manifest.json` |
| build | `usd/build.py` (one process per room) | textures, materials, shell, check-in room, equipment, marker, props, lights, cameras (incl. D455 exam cameras + stands) | `<id>.usd`, `textures/` |
| validate | `pipeline/validate.py` | Isaac-Sim checks (03 §3.4) | `results.json` |
| report | `metadata/` + `preview/` | metadata JSON, floor plan, CSV, summary, contact sheet | `<id>.json`, `<id>_plan.png`, … |

Every room gets its own random streams: `random.Random("<seed>:<index>:<attempt>:<stream>")`. The
same seed always gives the same rooms, and adding rooms (a larger `count`) does not change the
existing ones. `--resume` and `--only` reuse the run's `manifest.json`, so specs and layouts stay
identical even when the code that builds the USD changes.

## 1.2 Coordinate frames

There are two frames:

* **Room frame**: all geometry is authored in it, and the layout, the floor plan and most metadata use it.
* **Stage frame**: the root prim `/Room` carries a `translate` + `rotateZ` (`export.placement`) that
  centres the room at (0, 0, 0) and turns it so the entrance's outside faces `door_facing` (−Y,
  towards the viewer). Its formula is `p_stage = rotateZ(yaw) · p_room + translate`. `<id>.json`
  gives the placement and the key anchors / cameras in both frames (`*_stage`).

Room frame:

* Meters, Z-up (Isaac Sim default stage).
* Origin = the X-ray room's interior floor corner at the **entrance end**. x runs along the room
  (0 … length), y across it (0 … width), and the floor top is at z = 0.
* Outer walls (`wall_thickness_m`) are built **outside** the footprint, so the footprint is the
  clear interior of the X-ray room.
* The **check-in / changing room is outside the footprint**, behind the entrance-end (west) wall,
  so its coordinates have x < 0.
* "Left/right" detector side = looking into the room from the entrance end (+X): left = north wall
  (y = width), right = south wall (y = 0).

Plan view (north corner check-in room, detector on the south wall):

```
            corridor
   ┌──────────────┬───────────────────────────────────────────────────────┐ north (y = W)
   │  CHECK-IN    │                     tube rail ═════════                │
 E ▯  bench       ▯ C  [entrance           TUBE + Front camera             │
   │  (x < 0)     │     marker]                     │ beam                 │
   └──────────────┤                                 │                      │
                  │      Right ○ ←── 1.4 m ──→ [marker] ←── 1.4 m ──→ ○ Left
                  │                [DETECTOR] Top camera (0.2 m out, looks down)
                  └───────────────────────────────────────────────────────┘ south (y = 0)
                  x = 0                                                    x = L
 E = entrance (outer door of the check-in room, from the corridor)   C = connecting door
 Front / Left / Right / Top = RealSense_D455_Front / _Left / _Right / _Top (left / right = the patient's,
 facing the detector)
```

## 1.3 Layout order and rules

Patient route: corridor → **entrance** (outer door of the check-in room) → **check-in room**
(changes) → **connecting door** → X-ray room → **entrance marker** → **floor marker**. The
check-in room is the only way into the X-ray room.

1. **Check-in room** outside the X-ray room, against its west wall, in the north or south corner
   (`changing_room_corner`), size from `room.changing_room`, with its own floor, ceiling and outer
   walls. The **connecting door** sits in the shared west wall and swings into the X-ray room; a
   clearance zone (`walk.door_clearance_m`) is kept in front of it.
2. **Entrance** = the check-in room's outer door from the corridor: on its west wall or on its outer
   side wall (in line with the X-ray room's north / south wall), by `entrance_wall` weight, falling
   back to the other wall when it does not fit. A sampled width wider than the wall allows is narrowed,
   down to `entrance.min_width_m` (noted in `layout_notes`). It swings out into the corridor.
3. **Wall stand** on the detector wall, at least `x_margin_m` from the end walls. With side exam
   cameras, it is also kept one tripod reach (about 1.6 m) from each end wall, so that both tripods
   fit at 1.4 m. When a table or stretcher is requested, the stand goes towards the far end of that
   range so the table has room.
4. **Tube stand** on the opposite wall. The rail length is clipped to the free wall, and its centre
   is shifted so the carriage reaches the stand position. Arm length = width − detector face offset
   − SID − rail/column/housing offsets (≥ `arm_min_length_m`). The SID range is clipped to what fits.
5. **Floor marker** centred on the detector, `stand_gap_m` in front of its face. **Entrance marker**
   `entrance_marker.distance_from_door_m` inside the connecting door (where the patient enters the
   X-ray room), facing into the room (inside the door clearance zone, so no prop is placed on it).
   **Exam-camera tripods** (`cameras.exam_cameras`, `RealSense_D455_Left` / `RealSense_D455_Right`): `radius_m`
   (1.4 m) from the detector centre, side-on to the patient on the floor marker (on the patient's
   left / right when facing the detector). If the spot leaves the room, hits a door zone, the beam
   corridor or another object, or blocks the walk, it swings around the detector centre at the same
   radius (`lateral_search`). If no spot works, the room is resampled. Tripods are floor obstacles.
6. **Keep-out zones** (no objects, walking allowed): beam corridor between the detector face and the
   collimator (`beam_corridor_half_width_m`), door swings and door clearances, marker + 0.3 m,
   tube rail strip.
7. **Check-in room furniture**: bench on a wall without a door, clear of a 0.3 m strip in front of
   each door (shortened if needed), hooks above the bench, shelf and mirror on other walls, optional
   chair. A walk check inside the check-in room (entrance → connecting door) must still pass.
8. **Table / stretcher** (free-standing, along x), then the **props** in order: generator cabinet,
   lead screen, apron rack, chairs, waste bin, step stool. Wall items stand flush against a wall face.
   An item that does not fit after 60 tries is **dropped** and listed in `<id>.json → props_dropped`.
9. **Walk check** after every placement: on a 5 cm grid with obstacles grown by `agent_radius_m`, a
   breadth-first search from just inside the connecting door must reach the floor marker. The
   check-in room has its own check, from the entrance to the connecting door.
10. **Cable runs**: a floor cable cover from the rail end to the end wall, and a wall conduit next to
    the wall stand.
11. **Ceiling panels**: one row along the whole X-ray room (as many as fit) and one 2×2 panel in the check-in room.
12. **Cameras** (`layout/cameras.py`, own random stream, so changing camera settings never changes the room):
    * `far_wall_left/right`: the east wall (opposite the connecting door), `wall_offset_m` off the
      wall and `ceiling_gap_m` below the ceiling. Left/right is as seen from the connecting door.
      With `auto_frame` (default), the solver (`layout/coverage.py`) does the following:
      1. It samples the patient's actions: standing on the marker (6 heights + arms), the grid path
         connecting door → marker (hips, head and feet every 0.4 m), lying on the table or
         stretcher, and the exam floor.
      2. It tries mount positions every 0.1 m from the camera's corner to the middle of the wall.
      3. At each position it aims at the angular centre of the points and takes the longest lens
         (6.5–18 mm) that frames them.
      4. It counts the points that are in frame and not hidden behind 3-D boxes of the stands,
         props and exam-camera heads, and picks the best-scoring position.
      * The union of both cameras must reach `coverage.required` (marker 100 %, walking body 95 %,
        support 90 %); otherwise the layout is resampled.
    * `checkin_corner`: the check-in room corner farthest from the connecting door.
    * `entrance_outside`: in front of the entrance (the check-in room's outer door).
    * Then position / target jitter and focal length are applied.
13. **Exam cameras** (Intel RealSense D455 RGB-D; `solve_exam_cameras`, own random stream). They record
    the patient's X-ray poses in the later patient pipeline:
    * `RealSense_D455_Left` / `RealSense_D455_Right`: on their tripods, lens at 1.0 m, **portrait** (upright camera, tall
      image, 87° vertical: feet to head side-on), aimed at the centre of the patient movement zone (marker outline +
      `movement_margin_m`, floor to `body_height_m`).
    * `RealSense_D455_Front`: on top of the tube housing (`offset_m` in the tube-head frame), facing the patient
      along the beam, portrait, aimed at the patient's centre.
    * `RealSense_D455_Top`: post on the detector housing top (`rise_m`) with an arm reaching `extension_m` (0.2 m)
      out from the detector face; landscape, it looks down at the patient (aimed at the floor centre of the movement zone, image
      width along the detector wall).
    * Every exam camera's USD `focusDistance` is the distance to its patient aim point (`focus_distance_m`),
      `fStop` 0. Each has two camera prims named `<rig>_RGB` and `<rig>_Depth`.
    * Each camera records `movement_coverage` (the fraction of movement-zone points in frame). A value
      below `min_movement_coverage` is a warning. A patient closer than the D455 minimum depth (0.6 m)
      is expected for `RealSense_D455_Top` (a tall patient's head) and is reported as a note plus
      `within_depth_range: false`.

## 1.4 Distributions

Categorical choices are independent weighted draws. They are not exact quotas as in
synthetic-humans, because layout rejections would break quotas. For small counts (e.g. 3 rooms) the
achieved shares therefore differ from the weights; `summary.json` shows configured vs achieved.
Two rules shift the shares slightly: a room is resampled when its layout fails, and the entrance
falls back to the check-in room's other wall when it does not fit. In the default 17.7 × 8.3 ft room,
the two 1.4 m tripods leave little floor beside the detector, so a requested table or stretcher is
dropped in roughly half the rooms (noted in `layout_notes`; `rooms.csv → support_placed`).
