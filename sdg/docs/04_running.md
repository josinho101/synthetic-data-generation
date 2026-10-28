# 4. Running the pipeline

## 4.1 Commands

```bash
cd synthetic-data-generation/sdg

.venv/bin/python scripts/run_pipeline.py                         # 2 humans x 1 room from the latest runs, Isaac GUI
.venv/bin/python scripts/run_pipeline.py --headless              # same, no window
.venv/bin/python scripts/run_pipeline.py --dry-run               # inputs + visit plan only
.venv/bin/python scripts/run_pipeline.py --humans 5 --rooms 2    # 5 x 2 = 10 visits, 5 SDs
.venv/bin/python scripts/run_pipeline.py --human-ids H0003,H0010 --room-ids R0002
.venv/bin/python scripts/run_pipeline.py --humans-root ../output/humans/run-20261019-200423
.venv/bin/python scripts/run_pipeline.py --projections PA,RLAT
.venv/bin/python scripts/run_pipeline.py --keep-open             # GUI stays open after the last visit
.venv/bin/python scripts/run_pipeline.py --no-overlay            # clean RGB images (annotation JSON still written)
.venv/bin/python scripts/run_pipeline.py --set sequence.idle_s.outside=4 --set poses.timing.fov_on_s=2
.venv/bin/python scripts/run_pipeline.py -v                      # with Isaac's own console output
```

## 4.2 Run order

1. **Configuration**: load `configs/*.yaml`, apply CLI flags and `--set`, validate.
2. **Inputs**: resolve the humans run and the rooms run, then select the ids ([03 §3.1](03_configuration.md#31-runyaml)).
3. **Plan**: build one visit plan per room × exam from the room's anchors, and compute each human's T7 (detector)
   height. The plan is printed as a numbered step list.
4. **SD folders**: a new run folder `output/sdg/run-<timestamp>/` and in it one SD per human (`SD.00001`, `SD.00002`, …),
   each with an `sd_info.json` (status `pending`).
5. **Isaac Sim**: start `python.sh isaac/run_exam.py --job <tmp>.json`. Visits run one after another in the same
   Isaac session, each on a fresh in-memory stage ([05](05_animation_in_isaac.md)).
6. **Summary**: read each `sd_info.json`, set the SD status, print one line per SD, and exit.

Visit order: for each human (SD), for each exam, for each room.

## 4.3 Selection examples

| Configuration | Humans used |
|---|---|
| defaults | newest humans run with finished humans → first 2 ids (H0001, H0002) |
| `--humans 5` | first 5 finished ids |
| `--human-ids H0007,H0002` | exactly these, in this order (an error if one is missing or failed) |
| `--humans-root /data/humans` | newest finished `run-*` inside `/data/humans` |
| `--humans-root /data/humans/run-20261019-200423` | that run |

Rooms are selected the same way.

## 4.4 GUI and headless

| | GUI (default) | `--headless` |
|---|---|---|
| Window | Isaac Sim opens and shows the animation | none |
| Speed | wall-clock (`isaac.realtime`) | as fast as possible |
| Animation | identical (fixed 1/fps time step) | identical |
| End | Isaac closes after the last visit (or stays open with `--keep-open`) | Isaac closes |
| Use | watching, checking poses, tuning | batch runs, servers |

Closing the GUI window during a run ends the run with an error.

## 4.5 Run time

| Part | Approx. |
|---|---|
| Isaac start | 15 s (first ever start: several minutes, shader compilation) |
| Stage set-up per visit | 15–25 s |
| Animation per chest visit | about 50 s of simulated time (GUI: the same in wall-clock time) |
| Headless total | about 80 s per visit |

## 4.6 Exit codes

| Code | Meaning |
|---|---|
| `0` | every visit ok |
| `1` | Isaac or animation error, or a visit failed |
| `2` | configuration or input error (nothing was started) |
| `124` | Isaac exceeded `isaac.run_timeout_s` and was terminated |
| `130` | interrupted with Ctrl+C (Isaac is terminated) |
