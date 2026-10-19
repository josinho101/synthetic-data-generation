# 1. Overview & architecture

## Goal

The X-ray room digital twin needs a population of synthetic patients (default 150) that walk
into the room and get positioned for chest PA / LLAT / RLAT and thoracic & lumbar spine
AP / LLAT / RLAT exposures. Animation and annotation happen later in Isaac Sim. **This module only
generates the humans.** Each one has to be:

* **distinct**: face, skin tone, height, build (BMI), sex, age and ethnicity are sampled from a
  configurable population;
* **Isaac-Sim ready**: a single USD per human with a UsdSkel skeleton and skinned meshes;
* **annotatable**: anatomical landmarks (vertebrae, ears, ...) are **joints of the skeleton**, so
  their world position can be read every frame while the human is animated.

## Pipeline at a glance

```
 configs/*.yaml
      │
      ▼
 [0] PREFLIGHT  (system Python + one Blender probe)
      Python / packages / Blender version / MPFB version / asset packs / gown assets /
      landmark anchors / output directory / GPU
      │  fail fast on any error
      ▼
 [1] SAMPLE  (system Python, stdlib only, ~0.3 s for 150 humans)
      exact quotas (sex, ethnicity, age band, somatotype, clothing) → per-human seed →
      height, age, macros, race mix, skin tone, face targets, eyes/hair, gown colour →
      uniqueness check → <run>/manifest.json  (fully resolved; no randomness left)
      │
      ▼
 [2] BUILD  (one headless Blender process per human, N in parallel)
      body → face → fit height → skin → bake texture → rig → eyes/body parts → clothing →
      landmark bones → measurements → anatomical skeleton → preview PNGs → USD export →
      metadata JSON
      │
      ▼
 [3] VALIDATE  (system Python, usd-core)
      SkelRoot / Skeleton / skinning / ≤4 influences / textures / units / landmark joints
      │
      ▼
 [4] REPORT
      population.csv · summary.json (configured vs achieved) · contact_sheet.png
```

## Process model

```
run_pipeline.py (orchestrator, system Python)
  ├── ThreadPoolExecutor(workers)
  │     ├── blender -b -P scripts/blender_entry.py -- build args.json result.json H0001.log
  │     ├── blender -b ... H0002
  │     └── ...
  └── collects result.json of each worker → validates USD → progress line on the console
```

* **One Blender process per human.** Memory never accumulates, a crash affects only that human,
  and any human can be rebuilt alone (`--only H0042`).
* **Two Python worlds.** The orchestrator runs in a normal venv (YAML, numpy, usd-core, Pillow).
  Code inside Blender (`sdg_humans/blender/`) only uses `bpy`, MPFB and the standard library, and
  reads the configuration from `resolved_config.json`. Snap-packaged Blender cannot easily
  install pip packages, so this split is deliberate.
* **Determinism.** The global `seed` and the human index derive a per-human seed
  (`sha256(seed:index:attempt)`). The manifest stores every resolved value, so a build depends
  only on its manifest entry and the asset files.

## Code map

```
synthetic-humans/
├── configs/                 YAML configuration (see 03_configuration.md)
├── scripts/                 command-line entry points
│   ├── run_pipeline.py      main entry (preflight → sample → build → validate → report)
│   ├── check_env.py         preflight only
│   ├── sample_population.py stage 1 only (dry-run tables)
│   ├── make_gown.py         generate hospital gown assets
│   ├── calibrate_anchors.py propose landmark anchor vertices
│   ├── validate_usd.py      validate USD files of a run
│   ├── contact_sheet.py     rebuild the preview grid
│   └── blender_entry.py     the ONLY script Blender runs; dispatches build/gown/calibrate/probe
├── sdg_humans/
│   ├── config/              loader.py (YAML + overrides) · schema.py (validation rules)
│   ├── sampling/            quotas · anthropometrics · somatotype · ethnicity · face · looks ·
│   │                        identity · manifest           (pure Python, unit tested)
│   ├── blender/             runs inside Blender: bootstrap · body · fit · geometry · skin · bake ·
│   │                        rig · eyes · assets · gown_style · landmarks · measure · preview ·
│   │                        usd_export · calibrate · probe · pipeline (build task)
│   │   ├── gown/            regions · profile · body_parts · extras · builder · texture ·
│   │   │                    mhclo_writer · run (gown task)
│   │   └── anatomy/         prims · axial · appendicular · build (bone meshes)
│   ├── pipeline/            orchestrator · blender_runner · validate
│   ├── metadata/            writer (per-human JSON) · report (CSV, summary, contact sheet)
│   ├── landmark_math.py     spine distribution maths (pure Python, unit tested)
│   ├── clothing_match.py    MPFB-style clothes keyword matching (pure Python, unit tested)
│   ├── preflight.py · progress.py · logging_setup.py · run_context.py · mpfb_locate.py · paths.py
├── assets/custom/hospital_gown/   generated gown MHCLO assets + fabric texture
├── logs/                    central per-run log copies (rotated) + helper-script logs
├── tests/                   pytest suite (no Blender needed)
└── docs/                    this documentation
```

Each module has one job and stays under about 200 lines.

## Known limitations

* **No hair, eyebrows or eyelashes without MakeHuman asset packs.** The pipeline uses them
  automatically once installed (see 02 §2.4).
* **Gown:** a single generated garment shape (three length/sleeve variants). There is no cloth
  simulation: the drape is rule-based, and the MPFB fit plus smoothing adapts it per body.
* **Anatomical skeleton** is procedural (tubes, ellipsoids, plates): proportions and positions are
  right, detailed bone shapes are not (doc 11).
* **Rest pose** is MPFB's A-pose; posture (kyphosis, lordosis amount, scoliosis) follows the body
  shape only.
* **Landmarks** are surface-based anthropometric estimates (06 §6.5), not imaging-derived anatomy.
* **Weight/BMI** come from the mesh volume. MPFB bodies cap at roughly BMI 39 (male) / 33
  (female) with the macros alone.
