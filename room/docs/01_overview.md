# 1. Overview, coordinate frame & layout rules

## 1.1 Pipeline

| Stage | Code | What happens | Output |
|---|---|---|---|
| preflight | `pipeline/orchestrator.py:preflight` | Python, packages, output folder, disk, asset paths | `preflight.json` |
| sample | `sampling/sampler.py` | seed → every random choice of a room (finishes, light, SID, heights, props wanted) | spec |
| layout | `layout/solver.py` | spec → floor positions; unsolvable → resample (`attempt + 1`) | `manifest.json` |
| build | `usd/build.py` (one process per room) | textures, materials, shell, changing room, equipment, marker, props, lights | `<id>.usd`, `textures/` |
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
* Origin = interior floor corner at the **entrance end**. x runs along the room (0 … length),
  y across it (0 … width), and the floor top is at z = 0.
* Outer walls (`wall_thickness_m`) are built **outside** the footprint, so the footprint is the
  clear interior.
* "Left/right" detector side = looking into the room from the entrance end (+X): left = north wall
  (y = width), right = south wall (y = 0).

## 1.3 Layout order and rules

1. **Changing room** in the north or south corner at x = 0, size from `room.changing_room`. It has
   partition walls (`partition_thickness_m`) and a door on its east side or its long inner side.
   The door swings into the changing room, and a clearance zone is kept in front of it.
2. **Entrance**: on the west wall next to the changing room, or (if it does not fit, or by weight)
   on the long wall opposite the changing room near the entrance end. It swings into the X-ray room.
3. **Wall stand** on the detector wall, at least `x_margin_m` from the changing room, the entrance
   and the end wall. When a table or stretcher is requested, the stand goes within 0.6 m of the far
   end so the table has room.
4. **Tube stand** on the opposite wall. The rail length is clipped to the free wall, and its centre
   is shifted so the carriage reaches the stand position. Arm length = width − detector face offset
   − SID − rail/column/housing offsets (≥ `arm_min_length_m`). The SID range is clipped to what fits.
5. **Floor marker** centred on the detector, `stand_gap_m` in front of its face. **Entrance marker**
   `entrance_marker.distance_from_door_m` inside the entrance door, facing into the room (inside the
   door clearance zone, so no prop is placed on it).
6. **Keep-out zones** (no objects, walking allowed): beam corridor between the detector face and the
   collimator (`beam_corridor_half_width_m`), door swings and door clearances, marker + 0.3 m,
   tube rail strip.
7. **Changing-room furniture**: bench on a wall without the door and outside the door swing (shortened
   if needed), hooks above the bench, shelf and mirror on other walls, optional chair.
8. **Table / stretcher** (free-standing, along x), then the **props** in order: generator cabinet,
   lead screen, apron rack, chairs, waste bin, step stool. Wall items stand flush against a wall face.
   An item that does not fit after 60 tries is **dropped** and listed in `<id>.json → props_dropped`.
9. **Walk check** after every placement: on a 5 cm grid with obstacles grown by `agent_radius_m`, a
   breadth-first search from the entrance must reach the inside of the changing room, the space in
   front of its door, and the floor marker.
10. **Cable runs**: a floor cable cover from the rail end to the end wall, and a wall conduit next to
    the wall stand.
11. **Ceiling panels**: one row along the exam area (as many as fit) and one 2×2 panel in the changing room.
12. **Cameras** (`layout/cameras.py`, own random stream, so changing camera settings never changes the room):
    * `far_wall_left/right`: the free span of the wall opposite the entrance (without the changing
      room), `wall_offset_m` off the wall and `ceiling_gap_m` below the ceiling. Left/right is as seen
      from the door. With `auto_frame` (default), the solver (`layout/coverage.py`) does the following:
      1. It samples the patient's actions: standing on the marker (6 heights + arms), the grid path
         entrance → changing door → marker (hips, head and feet every 0.4 m), lying on the table or
         stretcher, and the exam floor.
      2. It tries mount positions every 0.1 m from the camera's corner to the middle of the wall.
      3. At each position it aims at the angular centre of the points and takes the longest lens
         (6.5–18 mm) that frames them.
      4. It counts the points that are in frame and not hidden behind 3-D boxes of the stands,
         partitions and props, and picks the best-scoring position.
      * The union of both cameras must reach `coverage.required` (marker 100 %, walking body 95 %,
        support 90 %); otherwise the layout is resampled.
    * `checkin_corner`: the changing-room corner farthest from its door.
    * `entrance_outside`: in front of the door.
    * Then position / target jitter and focal length are applied.

## 1.4 Distributions

Categorical choices are independent weighted draws. They are not exact quotas as in
synthetic-humans, because layout rejections would break quotas. For small counts (e.g. 3 rooms) the
achieved shares therefore differ from the weights; `summary.json` shows configured vs achieved.
Two rules shift the shares slightly: a room is resampled when its layout fails, and the entrance
falls back from the west wall to the long wall when the changing room leaves too little wall.
