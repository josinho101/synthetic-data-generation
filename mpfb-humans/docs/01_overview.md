# 1. Overview & architecture

## Goal

The X-ray room digital twin needs a population of synthetic patients (default 150) that walk
into the room and get positioned for chest PA / LLAT / RLAT and thoracic & lumbar spine
AP / LLAT / RLAT exposures. Animation and annotation happen later in Isaac Sim. **This module only
generates the humans.** Each one has to be:

* **distinct**: face, skin tone, height, build (BMI), sex, age and ethnicity are sampled from a
  configurable population;
* **Isaac-Sim ready**: a single USD per human with a UsdSkel skeleton and skinned meshes;
* **anatomical**: a skeleton from a swappable skeletal layer (default: the Z-Anatomy bones fitted
  into the body, with an anatomical rig, see [14](14_skeleton_layer.md));
* **annotatable**: anatomical landmarks (vertebrae, ears, ...) are stored in `<id>.json`. With the
  `procedural` / `none` layers they are also **joints of the MPFB skeleton**, so their world position
  can be read every frame while the human is animated.

## Pipeline at a glance

```
 configs/*.yaml
      │
      ▼
 [0] PREFLIGHT  (system Python + one Blender probe)
      Python / packages / Blender version / MPFB version / asset packs / gown assets /
      landmark anchors / skeletal layer / output directory / GPU
      │  fail fast on any error
      ▼
 [1] SAMPLE  (system Python, stdlib only, ~0.3 s for 150 humans)
      exact quotas (sex, ethnicity, age band, somatotype, clothing) → per-human seed →
      height, age, macros, race mix, skin tone, face targets, eyes/hair, colours →
      uniqueness check → <run>/manifest.json  (fully resolved; no randomness left)
      │
      ▼
 [2] BUILD  (one headless Blender process per human, N in parallel)
      body → face → fit height → skin → bake texture → rig → eyes/body parts → clothing →
      floor (footwear lift) → landmark bones → measurements → [procedural: bone meshes |
      zanatomy: save closed body] → finalize → preview PNGs → USD export → metadata JSON
      │
      ▼
 [3] USD POST + SKELETAL LAYER  (system Python, usd-core; zanatomy also torch)
      clothing holes · SkelOrigin root joint · zanatomy: fit bones, swap rig, re-skin
      │
      ▼
 [4] VALIDATE  (system Python, usd-core)
      SkelRoot / Skeleton / skinning / ≤4 influences / textures / units / metadata joints
      (+ optional animation <id>_anim.usda, MPFB rig only)
      │
      ▼
 [5] REPORT
      population.csv · summary.json (configured vs achieved) · contact_sheet.png
```

## Process model

```
run_pipeline.py (orchestrator, system Python)
  ├── ThreadPoolExecutor(workers)
  │     ├── blender -b -P scripts/blender_entry.py -- build args.json result.json H0001.log
  │     ├── blender -b ... H0002
  │     └── ...
  └── collects result.json of each worker → USD post → skeletal layer → validates USD
      → progress line on the console
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
mpfb-humans/
├── configs/                 YAML configuration (see 03_configuration.md)
├── scripts/                 command-line entry points
│   ├── run_pipeline.py      main entry (preflight → sample → build → validate → report)
│   ├── check_env.py         preflight only
│   ├── sample_population.py stage 1 only (dry-run tables)
│   ├── make_gown.py         generate hospital gown assets
│   ├── install_asset_packs.py  download / install MakeHuman asset packs
│   ├── calibrate_anchors.py propose landmark anchor vertices
│   ├── validate_usd.py      validate USD files of a run
│   ├── contact_sheet.py     rebuild the preview grid
│   ├── garment_catalog.py   render every catalogued garment on reference humans
│   ├── pose_exams.py        X-ray exam poses for one human (MPFB rig)
│   ├── build_zanatomy_reference.py  one-time Z-Anatomy reference package → assets/zanatomy
│   └── blender_entry.py     the ONLY script Blender runs; dispatches build/gown/calibrate/catalog/probe
├── sdg_humans/
│   ├── config/              loader.py (YAML + overrides) · schema.py (validation rules)
│   ├── sampling/            quotas · anthropometrics · somatotype · ethnicity · face · looks ·
│   │                        identity · manifest           (pure Python, unit tested)
│   ├── blender/             runs inside Blender: bootstrap · body · fit · geometry · skin · bake ·
│   │                        rig · eyes · assets · gown_style · landmarks · measure · preview ·
│   │                        usd_export · calibrate · catalog · probe · pipeline (build task)
│   │   ├── gown/            regions · profile · body_parts · extras · builder · texture ·
│   │   │                    mhclo_writer · run (gown task)
│   │   └── anatomy/         prims · axial · appendicular · build (procedural bone meshes)
│   ├── skeleton/            skeletal layers: registry · procedural (+ none) · zanatomy/ (fit, weights,
│   │                        usd_rig, reference)                          (doc 14)
│   ├── pipeline/            orchestrator · blender_runner · validate
│   ├── metadata/            writer (per-human JSON) · report (CSV, summary, contact sheet)
│   ├── landmark_math.py     spine distribution maths (pure Python, unit tested)
│   ├── landmark_rules.py · anatomy_rules.py · pose_rules.py · pose_usd.py
│   │                        anchors, derived joints, exam posing (shared with the MHR pipeline, doc 13)
│   ├── clothing_match.py    MPFB-style clothes keyword matching (pure Python, unit tested)
│   ├── usd_post.py          post-export USD fixes (clothing holes, root joint)
│   ├── isaac_landmarks.py   read landmark joints in Isaac Sim (pxr only)
│   ├── asset_packs.py · preflight.py · progress.py · logging_setup.py · run_context.py · mpfb_locate.py · paths.py
├── assets/custom/hospital_gown/   generated gown / skirt MHCLO assets + fabric texture
├── assets/zanatomy/         Z-Anatomy reference package (built once, gitignored)
├── isaac/                   procedural animation + Isaac Sim playback (MPFB rig)
├── logs/                    central per-run log copies (rotated) + helper-script logs
├── tests/                   pytest suite (no Blender needed)
└── docs/                    this documentation
```

Each module has one job and stays under about 200 lines.

## Known limitations

* **No hair, eyebrows or eyelashes without MakeHuman asset packs.** The pipeline uses them
  automatically once installed (see 02 §2.4).
* **No cloth simulation:** garments deform by skinning only. The generated gown (not in the shipped
  variants) is a single rule-based shape in three length/sleeve variants.
* **Anatomical skeleton:** the default Z-Anatomy layer is one male reference skeleton fitted per
  human (pelvis stays male-shaped in women; doc 14). The `procedural` layer is schematic (tubes,
  ellipsoids, plates; doc 11).
* **Z-Anatomy rig vs animation:** exam posing, `export.animation` and `../sdg` retargeting drive MPFB
  joint names and do not apply to `zanatomy` humans.
* **Rest pose** is MPFB's A-pose. Kyphosis, lordosis and scoliosis are sampled per human for the
  vertebral landmarks only (`spine_shape`); the skin is not reshaped.
* **Landmarks** are surface-based anthropometric estimates (06 §6.5), not imaging-derived anatomy.
* **Weight/BMI** come from the mesh volume. MPFB bodies cap at roughly BMI 39 (male) / 33
  (female) with the macros alone.
