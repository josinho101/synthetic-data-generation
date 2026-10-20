# 9. Logging & monitoring

## 9.1 Log files

| File | Level | Written by | Content |
|---|---|---|---|
| `<run>/logs/pipeline.log` | INFO+ | orchestrator | preflight, sampling, worker start/finish, validation, report |
| `<run>/logs/errors.log` | ERROR+ | orchestrator | every error with context |
| `<run>/logs/humans/<id>.log` | INFO+ (`worker_level`) | Blender worker | each build step with duration, measurements, asset choices, warnings, tracebacks (solver iterations at DEBUG) |
| `<run>/logs/humans/<id>.blender.log` | raw | Blender process | Blender / MPFB / Cycles console output |
| `synthetic-humans/logs/run-<timestamp>.log` | same as `run_file` | orchestrator | central copy of `pipeline.log` |
| `synthetic-humans/logs/{make_gown,calibrate_anchors,preflight_probe}.log` | DEBUG+ | helper scripts | |

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
[preflight] OK   blender           Blender 5.2.2
...
[sample]    150 humans | male 75 female 75 | south_asian 30 ... | 0.3s -> /…/manifest.json
[build]     150 to build with 1 worker(s)
[build]  start  H0001 F 77y south_asian     mesomorph_ectomorph  target 162.6cm gown
[build]  [   1/150 |   0.7%] OK   H0001 F 77y south_asian     mesomorph_ectomorph  163.0cm 48.8kg BMI 18.4 gown | 26.1s | elapsed 26s ETA 1h04m45s
[build]  [   2/150 |   1.3%] WARN H0002 M 34y caucasian       endomorph            181.2cm 112.4kg BMI 34.2 gown | 27.3s | elapsed 53s ETA 1h05m10s | warnings: 1
...
[report]    configured vs achieved
  sex
    male                   configured   50.0%   achieved   75 ( 50.0%)
  ...
  height_cm  min   146.1  mean   168.0  max   195.0
[done]      run-20261018-211500 | 149 ok, 1 warn, 0 failed | total 1h07m -> /…/run-20261018-211500
```

Each finished human prints: progress count and percentage, status (OK / WARN / FAIL), identity
summary, achieved height/weight/BMI, clothing, build time, elapsed time and ETA. A failed human also
prints its error and log path.

## 9.4 Diagnosing a failed human

1. Find it: `summary.json → failed`, `errors.log`, or the `FAIL` console line.
2. Open `logs/humans/<id>.log`: the last `step … ...` line without `done` is the failing step.
   The traceback follows.
3. If needed, read `logs/humans/<id>.blender.log` for MPFB / Blender messages.
4. `work/<id>/build_args.json` holds the exact worker input. Re-run one human with
   `run_pipeline.py --only <id> --run-dir <run>`.

Example worker log excerpt (with `worker_level: DEBUG`):

```
20:51:02 | INFO  | sdg_humans.blender.pipeline:31 | step fit ...
20:51:02 | DEBUG | sdg_humans.blender.fit:33 | height solver it=0 macro=0.5000 height=165.21cm error=+2.61
20:51:02 | DEBUG | sdg_humans.blender.fit:33 | height solver it=1 macro=0.2500 height=158.02cm error=-4.58
...
20:51:03 | INFO  | sdg_humans.blender.fit:60 | volume=48.3L mass=48.8kg height=163.0cm BMI=18.4
20:51:03 | INFO  | sdg_humans.blender.pipeline:34 | step fit done in 0.55s
```
