# 9. Logging & monitoring

## 9.1 Log files

| File | Level | Written by | Content |
|---|---|---|---|
| `<run>/logs/pipeline.log` | INFO+ | orchestrator | preflight, sampling, worker start/finish, validation, report |
| `<run>/logs/errors.log` | ERROR+ | orchestrator | every error with context |
| `<run>/logs/humans/<id>.log` | INFO+ (`worker_level`) | Blender worker | each build step with duration, measurements, asset choices, warnings, tracebacks (solver iterations at DEBUG) |
| `<run>/logs/humans/<id>.blender.log` | raw | Blender process | Blender / MPFB / Cycles console output |
| `mpfb-humans/logs/run-<timestamp>.log` | same as `run_file` | orchestrator | central copy of `pipeline.log` |
| `mpfb-humans/logs/{make_gown,calibrate_anchors,preflight_probe}.log` | DEBUG+ | helper scripts | |

**Rotation per run:** every run writes new files into its own run directory. In the central
`logs/` folder only the newest `keep_last_runs` (20) `run-*.log` files are kept, and older ones are
deleted at the start of a run.

## 9.2 `configs/logging.yaml`

The **default level is INFO** (console, files and workers). For troubleshooting, set
`worker_level`, `handlers.run_file.level` and `root.level` to `DEBUG`.

```yaml
keep_last_runs: 20
worker_level: INFO
worker_format: "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
dict_config:                 # standard logging.config.dictConfig
  version: 1
  formatters: {detailed: {...}, console: {format: "%(message)s"}}
  handlers:
    console:  {class: logging.StreamHandler, level: INFO, ...}
    run_file: {class: logging.FileHandler, level: INFO, filename: "{run_dir}/logs/pipeline.log"}
    errors:   {class: logging.FileHandler, level: ERROR, filename: "{run_dir}/logs/errors.log"}
  root: {level: INFO, handlers: [console, run_file, errors]}
```

* For a quieter console, set `handlers.console.level: WARNING`.
* For more console detail, set `handlers.console.level: DEBUG`.
* Any standard handler works (e.g. `logging.handlers.RotatingFileHandler`).

## 9.3 Console output

```
[run]       run-20261018-211500 -> /…/output/humans/run-20261018-211500
[preflight] OK   python            Python 3.12.3
[preflight] OK   blender           Blender 5.2.2 LTS
...
[preflight] OK   skeleton layer    zanatomy: zanatomy-ref-1 (156 bones, 158 meshes)
...
[sample]    150 humans | male 75 female 75 | south_asian 30 ... | 0.3s -> /…/manifest.json
[build]     150 to build with 1 worker(s)
[build]  start  H0001 F 64y caucasian       mesomorph            target 167.6cm full_outfit
H0001: USD post-processing {'clothing_holes': {...}, 'root_joint': {'name': 'SkelOrigin', 'added': True}}
H0001: skeleton fit in 10.1s, landmarks median 9.0 mm, exposed ~0.022
H0001: [skeleton] zanatomy layer done in 17.6s {'landmark_residual_mm': {'median': 9.0, 'p90': 30.0}, ...}
[build]  [   1/150 |   0.7%] OK   H0001 F 64y caucasian       mesomorph            167.8cm 54.1kg BMI 19.2 full_outfit | 49.0s | elapsed 1m26s ETA 3h34m
[build]  [   2/150 |   1.3%] WARN H0002 M 34y caucasian       endomorph            181.2cm 112.4kg BMI 34.2 top_and_jeans | 52.3s | elapsed 2m45s ETA 3h20m | warnings: 1
...
[report]    configured vs achieved
  sex
    male                   configured   50.0%   achieved   75 ( 50.0%)
  ...
  height_cm  min   146.1  mean   168.0  max   195.0
[done]      run-20261018-211500 | 149 ok, 1 warn, 0 failed | total 1h07m -> /…/run-20261018-211500
```

Each finished human prints: progress count and percentage, status (OK / WARN / FAIL), identity
summary, achieved height/weight/BMI, clothing variant, Blender build time, elapsed time and ETA. The
lines before it log the USD post-processing and the skeletal layer (fit residuals). A failed human also
prints its error and log path.

## 9.4 Diagnosing a failed human

1. Find it: `summary.json → failed`, `errors.log`, or the `FAIL` console line.
2. Open `logs/humans/<id>.log`: the last `step … ...` line without `done` is the failing step.
   The traceback follows.
   Errors after the Blender build (`USD post-processing: …`, `skeletal layer: …`, `USD validation: …`)
   are in `pipeline.log` / `errors.log` instead, with the traceback.
3. If needed, read `logs/humans/<id>.blender.log` for MPFB / Blender messages.
4. `work/<id>/build_args.json` holds the exact worker input. Re-run one human with
   `run_pipeline.py --only <id> --run-dir <run>`.

Example worker log excerpt (with `worker_level: DEBUG`):

```
20:51:02 | INFO  | sdg_humans.blender.pipeline:30 | step fit ...
20:51:02 | DEBUG | sdg_humans.blender.fit:39 | height solver it=0 macro=0.5000 height=165.21cm error=+2.61
20:51:02 | DEBUG | sdg_humans.blender.fit:39 | height solver it=1 macro=0.2500 height=158.02cm error=-4.58
...
20:51:03 | INFO  | sdg_humans.blender.fit:65 | volume=48.3L mass=48.8kg height=163.0cm BMI=18.4
20:51:03 | INFO  | sdg_humans.blender.pipeline:33 | step fit done in 0.55s
```
