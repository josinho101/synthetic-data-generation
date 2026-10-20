# room

Config-driven generator of **synthetic X-ray rooms** for the X-ray room digital twin. Every room is
a self-contained, **Isaac-Sim-ready USD**: meters, Z-up, UsdPreviewSurface materials with
procedural textures, UsdLux lights, physics colliders and semantic labels. The pipeline works like
[synthetic-humans](../synthetic-humans/README.md): YAML configs + a seed → N distinct, reproducible
rooms, each in its own folder with metadata and a floor plan.

Every room has:

- a **17.7 × 8.3 ft (5.395 × 2.530 m)** interior footprint and a room height of 2.60–3.00 m (both
  configurable: fixed or a range, in feet or meters);
- an **entrance door** from the corridor straight into the X-ray room;
- a small **check-in / changing room** inside the footprint, with its own door into the X-ray room
  (bench, coat hooks, gown shelf with folded gowns, optional mirror and chair). Patient flow:
  entrance → changing room → back into the X-ray room → floor marker;
- a **wall bucky**: flat-panel detector on a vertical wall stand. The carriage height is adjustable;
  the detector has side grip handles and an optional top bar, plus an active-area / AEC marking;
- a **floor-mounted X-ray tube on a rail** (optional floor-to-ceiling column with ceiling rail),
  aimed at the detector at a sampled **SID**. Tube housing, collimator with light window and handle;
- a **floor marker** where the patient stands: tape outline, footprints and a centre line, plus a
  `PatientStand` anchor that a synthetic human can be referenced onto. Tape colours are dark
  (amber, charcoal, blue) and always darkened to contrast with the floor;
- an **entrance marker** just inside the entrance door where the patient first stands still
  (tape outline + footprints facing into the room, `EntranceStand` anchor);
- **diffuse ceiling panel lights** (2×2 / 2×4 ft troffers). Illuminance is drawn from 100–1000 lux
  (mean 500). Colour temperature is drawn by class: warm 2700–3500 K, neutral 3500–4500 K, cool 4500–6500 K;
- **mild glare** on equipment surfaces: semi-gloss clearcoat paint and chrome grips and rail;
- **cameras** (configurable in `configs/cameras.yaml`): two high in the corners of the wall
  opposite the entrance (`Cam_FarLeft`, `Cam_FarRight`), one in the check-in room (`Cam_CheckIn`),
  and `Viewer_Entrance` outside the door. All are `UsdGeom.Camera` prims with resolution, ready for
  Replicator. The two X-ray-room cameras are **auto-framed for patient coverage**: their position along
  the far wall, aim and lens are solved so that together they see the patient on the floor marker (head
  to feet, arms out), the whole walk entrance → changing room → marker, and the patient on the table or
  stretcher, with occlusion by equipment and props checked. A room that misses this is resampled;
  `<id>.json → camera_coverage` reports the result;
- **placement on import**: the room is centred on the stage origin and turned so the **entrance door
  faces the viewer** (−Y by default), and Isaac opens the file with the viewport in front of the door;
- **variations**: wall finish (white / beige / gray / tiled), floor (vinyl / tile / concrete),
  detector on the **left or right** wall, changing-room corner, door positions and angles, **table
  or stretcher or neither**, clutter (chairs, lead-apron rack, mobile lead screen, generator
  cabinet, waste bin, step stool, cable runs). Colours are jittered per room, and the floor always
  differs from the walls by at least ΔE 10 (`materials.min_floor_wall_delta_e`).

A layout solver places everything without overlaps. The tube→detector beam corridor, the door
swings and the floor marker stay clear, and a grid search checks that a person can walk from the
entrance to the changing room and on to the floor marker.

## Setup (one time, ~2 min)

| Item | Version |
|---|---|
| Python | ≥ 3.10 (tested 3.12) |
| Packages | `pyyaml numpy usd-core pillow pytest` (no Blender, no Isaac Sim needed to generate) |
| Blender | optional, only for `scripts/blender_preview.py` QA renders |

```bash
cd synthetic-data-generation/room
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/check_env.py          # must end with [preflight] PASSED
```

`configs/export.yaml → output_root` is where runs go (default
`synthetic-data-generation/output/rooms`).

## Quick start

```bash
.venv/bin/python scripts/run_pipeline.py                         # variations.count rooms (default 1)
.venv/bin/python scripts/run_pipeline.py --count 20 --seed 7     # 20 other rooms
.venv/bin/python scripts/run_pipeline.py --set room.footprint_ft=[20,10]          # any config value
.venv/bin/python scripts/run_pipeline.py --height 2.9                            # fixed room height (m)
.venv/bin/python scripts/run_pipeline.py --set room.ceiling_height_ft=9          # ... or in feet
.venv/bin/python scripts/run_pipeline.py --set cameras.cameras.Cam_CheckIn.enabled=false
.venv/bin/python scripts/run_pipeline.py --set variations.patient_support="{none: 0, table: 1, stretcher: 0}"
.venv/bin/python scripts/run_pipeline.py --resume --run-dir <output_root>/run-<timestamp>
.venv/bin/python scripts/run_pipeline.py --only R0002 --run-dir <output_root>/run-<timestamp>  # same spec, rebuilt
.venv/bin/python scripts/sample_rooms.py --count 12 --plans /tmp/plans   # layouts + floor plans only, no USD
```

A room takes about 1 s. Each run creates `<output_root>/run-<timestamp>/`:

```
run-20261020-090218/
├── rooms/R0001/{R0001.usd, R0001.json, R0001_plan.png, textures/}
├── manifest.json  rooms.csv  summary.json  results.json  contact_sheet.png
├── config_snapshot/  resolved_config.json  preflight.json
└── logs/{pipeline.log, errors.log, rooms/R0001.log}
```

Exit codes: `0` all rooms ok/warn · `1` at least one failed · `2` config or preflight error.

## Using the rooms in Isaac Sim

* *File → Open* `R0001.usd`: the room sits centred at the origin with the entrance door facing the
  viewer, and the viewport starts in front of the door (`export.placement`). You can also drag the
  file into your stage as a reference (the placement comes along). Keep the folder intact, because
  textures are referenced relative to the USD.
* Cameras: pick `Cam_FarLeft`, `Cam_FarRight`, `Cam_CheckIn` or `Viewer_Entrance` in the viewport
  camera menu. `isaac/capture_cameras.py` renders RGB, segmentation and depth from them with
  Replicator.
* Room plus patient: `python isaac/compose_scene.py R0001.usd --human <humans run>/humans/H0001/H0001.usd`
  writes `scene_R0001_H0001.usda`. The human stands on the marker facing the detector, and the
  detector and tube are set to the human's T7 (chest) height. See [isaac/README.md](isaac/README.md).
* Light calibration (once): see [docs/03_usd_isaac_sim.md](docs/03_usd_isaac_sim.md#lux-calibration).

## Configure

| File | Controls |
|---|---|
| `configs/variations.yaml` | count, seed, weights of every categorical choice (detector side, finishes, CCT class, table/stretcher, …) |
| `configs/room.yaml` | footprint, room height (`ceiling_height_m` / `ceiling_height_ft`), wall thickness, entrance and changing-room sizes, doors, walk-path clearance |
| `configs/equipment.yaml` | wall stand, detector, grips, tube stand, rail, SID, floor marker; optional `asset:` per part to use real CAD/USD |
| `configs/materials.yaml` | wall / floor / ceiling / door finishes, colour jitter, glare level and equipment finishes |
| `configs/lighting.yaml` | lux distribution, CCT ranges, panel sizes and counts, indirect gain, `lux_calibration` |
| `configs/props.yaml` | clutter items (probability / count, size, colours, wall or free-standing), table / stretcher, changing-room items |
| `configs/cameras.yaml` | cameras: mount, target, focal length, resolution, jitter, housing; enable/disable each |
| `configs/export.yaml` | output root, workers, USD format, **placement** (door facing, origin, viewport), colliders, rigid bodies, semantics, preview |
| `configs/logging.yaml` | log levels, files, rotation |

Equipment dimensions are typical radiography values, **not GE specifications**. Put the values
from the product spec sheet into `equipment.yaml`, or point `wall_stand.asset` / `tube_stand.asset`
at a converted CAD USD.

## Documentation

1. [Overview, coordinate frame & layout rules](docs/01_overview.md)
2. [Configuration reference](docs/02_configuration.md)
3. [USD structure & Isaac Sim](docs/03_usd_isaac_sim.md)
4. [Metadata schema](docs/04_metadata_schema.md)
5. [Isaac Sim scene composition](isaac/README.md)

## Tests

```bash
.venv/bin/python -m pytest -q tests      # config, sampling, layout, photometry, USD build (~5 s)
```

## QA renders (optional, Blender)

```bash
blender -b --python scripts/blender_preview.py -- <run>/rooms/R0001/R0001.usd          # Workbench, ~10 s
blender -b --python scripts/blender_preview.py -- <run>/rooms/R0001/R0001.usd out --eevee
blender -b --python scripts/blender_preview.py -- <run>/rooms/R0001/R0001.usd out --cameras  # + each USD camera
```

These write `R0001_view1/2/3.png`, `R0001_top.png` and, with `--cameras`, `R0001_cam_<name>.png`. Blender light units differ from RTX, so use
the renders to check geometry, not brightness.
