# 6. Output schema

## 6.1 Folder layout

```
output/sdg/                             run.output_root (default <repo>/output/sdg)
└── run-20261021-193000/                one folder per pipeline run (run.run_dir_format)
    ├── SD.00001/                       one SD = one human
    │   ├── sd_info.json
    │   └── CHEST/                      one folder per exam (later SPINE/)
    │       ├── timeline.txt
    │       ├── frames.csv              frame -> simulated time, step, FOV light (doc 10)
    │       └── FAR_LEFT/{RGB,Depth,Depth_Preview}/   one folder per recorded camera: RGB/000001.png, … (doc 10)
    └── SD.00002/
        └── ...
```

* Every run gets a new `run-<YYYYmmdd-HHMMSS>` folder (a `-2`, `-3` suffix if two runs start in the same second),
  so earlier runs are never overwritten. SDs are numbered from `SD.00001` in each run; an SD is identified by
  run + SD (`run-20261021-193000/SD.00001`). Running the same human again creates a new SD in the new run.
* With more than one room per run, each room gets its own folder: `CHEST/R0001/timeline.txt`, `CHEST/R0002/timeline.txt`.
* There are no USD or log files in the SD. The console is the run log ([07](07_logging_and_errors.md)). Image frames
  are described in [10](10_capture.md).

## 6.2 `sd_info.json`

Written by the host before Isaac starts (status `pending`), updated by Isaac after each visit, and finalised by the
host.

| Field | Content |
|---|---|
| `sd` | SD name |
| `status` | `ok` (every visit ok), `failed`, or `pending` (Isaac did not reach the visit) |
| `created` | ISO time the SD was created |
| `human` | `id`, `usd`, `json`, `run` (source paths), `height_cm`, `chest_height_m` (T7, the detector / tube height used) |
| `rooms[]` | `id`, `usd`, `run` for each room of the run |
| `exams` | exam → projections, as run |
| `isaac_version` | content of Isaac's `VERSION` file |
| `capture` | `groups` (e.g. `{"side": "LEFT"}`: the camera this SD records from each camera group, used to balance the dataset across runs), `cameras` (folder names), `fps` (captured images per second), `sim_fps` (`isaac.fps`), `every_n_frames` (`sim_fps / fps`); `null` with `--no-capture` |
| `visits` | `"<EXAM>/<room id>"` → `status` (`ok` / `failed` / `pending`), `timeline` (path), `finished` (ISO time), `error` (message, when failed) |

Example:

```json
{
  "sd": "SD.00002",
  "run": "run-20261021-193000",
  "status": "ok",
  "human": {"id": "H0002", "run": ".../output/humans/run-20261019-200423", "height_cm": 154.67, "chest_height_m": 1.1702, ...},
  "rooms": [{"id": "R0001", "run": ".../output/rooms/run-20261020-184851", ...}],
  "exams": {"CHEST": ["PA", "LLAT", "RLAT"]},
  "isaac_version": "6.2.0-rc.14+release.52805.02189a84.gl",
  "visits": {"CHEST/R0001": {"status": "ok", "timeline": ".../run-20261021-193000/SD.00002/CHEST/timeline.txt", "finished": "2026-10-20T21:21:55.371"}}
}
```

## 6.3 `timeline.txt`

Header lines start with `#`. Every event line has this format:

```
<wall-clock ISO time, ms>  t=<simulated seconds since load, 8.2f>s  <event>
```

```
# sd: SD.00002
# human: H0002 (run-20261019-200423)
# room: R0001 (run-20261020-184851)
# exam: CHEST
# projections: PA, LLAT, RLAT
# started: 2026-10-20T21:19:14.385
2026-10-20T21:20:55.320  t=    0.00s  Model loaded outside the room
2026-10-20T21:20:55.958  t=    0.50s  Model standing outside the entrance
2026-10-20T21:20:58.284  t=    2.50s  Model started walking into the check-in room
2026-10-20T21:21:01.039  t=    4.87s  Model entered the check-in room
...
2026-10-20T21:21:19.378  t=   20.07s  PA: FOV light ON
2026-10-20T21:21:20.656  t=   21.10s  PA: FOV light OFF
...
2026-10-20T21:21:53.297  t=   48.60s  Model standing outside
# status: ok
```

The last line is `# status: ok` or `# status: failed`. A failed visit also has an event line `ERROR: <message>`
before it.

### Events

| Phase | Event text |
|---|---|
| arrival | `Model loaded outside the room`, `Model standing outside the entrance` |
| check-in | `Model started walking into the check-in room`, `Model entered the check-in room`, (`Model standing in the check-in room` if `idle_s.check_in` > 0) |
| entrance marker | `Model started walking into the X-ray room`, `Model standing on the entrance marker`, `Model idle on the entrance marker` |
| detector marker | `Model started walking to the detector marker`, `Model reached the detector marker`, `Model turning to face the detector`, `Model standing on the detector marker, facing the detector`, `Model idle on the detector marker` |
| per projection `<P>` | `<P>: Model turning left / right / to face the detector (<label>)`, `<P>: Model moving hands to hands-on-hip / hands-on-head pose`, `<P>: Model in … pose`, `<P>: FOV light ON`, `<P>: FOV light OFF`, `<P>: Model lowering the arms`, `<P>: Model arms down, <label> done` |
| exit | `Model walking back to the door marker`, `Model standing on the door marker`, `Model idle on the door marker`, `Model started leaving the room`, `Model left the room`, `Model standing outside` |

"started …" events are written when the step starts. "entered / reached / standing / in … pose / done" events are
written when it has finished. The time between `FOV light ON` and `FOV light OFF` is `poses.timing.fov_on_s`
(1.0 s, ±1 frame).
