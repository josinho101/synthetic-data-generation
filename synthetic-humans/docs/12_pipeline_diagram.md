# 12. Pipeline diagram (high level)

How the synthetic-patient generator turns a parameter file into a population of distinct,
rigged, landmark-annotated humans for Isaac Sim, and how the same pipeline scales from 1 to N.

```mermaid
flowchart TB
  subgraph P["① PARAMETER SPACE: YAML configs, no code changes"]
    direction LR
    P1["population.yaml<br/>count · seed · quotas for sex,<br/>age, ethnicity, somatotype<br/>height distributions"]
    P2["appearance.yaml<br/>race mix · Monk skin tone<br/>face detail ranges · eyes · hair"]
    P3["clothing.yaml + gown.yaml<br/>hospital gown · shirt + jeans · skirt<br/>colours · length · sleeves"]
    P4["landmarks.yaml + anatomy.yaml<br/>84 landmark anchors<br/>~80 anatomical bone meshes"]
    P5["export.yaml<br/>workers · USD · bake<br/>preview · animation"]
  end

  PF{{"Preflight<br/>Python · Blender · MPFB · asset packs · GPU<br/>fail fast before any compute"}}

  subgraph S["② SAMPLING ENGINE: pure Python, ~0.3 s for 150 humans"]
    direction LR
    S1["Exact quotas<br/>largest remainder +<br/>stratified interleaving"] --> S2["Per-human seed<br/>sha256 of seed, index, attempt"]
    S2 --> S3["Free attributes<br/>age · height · body macros<br/>race mix · skin · face · looks"]
    S3 --> S4["Uniqueness check<br/>min feature distance<br/>redraw if too similar"]
  end

  M[("manifest.json<br/>fully resolved spec per human<br/>no randomness left")]

  subgraph B["③ BUILD ENGINE: Blender + MPFB, one headless process per human, N in parallel"]
    direction LR
    B1["Body and identity<br/>MPFB macros · face targets<br/>height fit · BMI from volume"] --> B2["Skin and looks<br/>tone-matched skin<br/>Cycles texture bake · hair, eyes"]
    B2 --> B3["Rig and clothing<br/>163-bone rig<br/>gown or MakeHuman garments"]
    B3 --> B4["Annotation<br/>84 landmark joints<br/>anatomical skeleton"]
    B4 --> B5["Export<br/>UsdSkel USD · previews<br/>metadata JSON"]
  end

  subgraph V["④ VALIDATE, ANIMATE, REPORT: usd-core"]
    direction LR
    V1["USD checks<br/>skeleton · skinning · units<br/>textures · landmark joints"] --> V2["Procedural animation<br/>idle, walk, jump, walk back"]
    V2 --> V3["Population report<br/>configured vs achieved<br/>CSV · contact sheet"]
  end

  O[("Per human<br/>H0001.usd · H0001_anim.usda<br/>H0001.json · previews · textures")]
  D["Isaac Sim X-ray room<br/>exam poses · cameras · labelled frames"]

  subgraph SC["SCALABILITY"]
    direction TB
    X1["Size is one parameter<br/>count: 1 → 150 → N"]
    X2["Horizontal scale-out<br/>N workers, ~1.5 GB RAM each"]
    X3["Fault isolation<br/>retries · resume · rebuild one human"]
    X4["Deterministic<br/>same seed → same population"]
    X5["Cost per human, per worker<br/>~90 s · ~60 MB on disk"]
  end

  P --> PF --> S --> M --> B --> V --> O --> D
  SC -.-> B

  classDef cfg fill:#fdf1d8,stroke:#b7791f,color:#3d2a06
  classDef smp fill:#e3eefc,stroke:#2b6cb0,color:#0f2747
  classDef bld fill:#dcf3ef,stroke:#2c7a7b,color:#0b3433
  classDef val fill:#ece7fb,stroke:#6b46c1,color:#2a1a56
  classDef out fill:#eef1f4,stroke:#4a5568,color:#1a202c
  classDef scl fill:#e5f5e3,stroke:#2f855a,color:#11351f
  class P1,P2,P3,P4,P5 cfg
  class S1,S2,S3,S4 smp
  class B1,B2,B3,B4,B5 bld
  class V1,V2,V3 val
  class PF,M,O,D out
  class X1,X2,X3,X4,X5 scl
```

## Reading the diagram

* **Parameterized.** Every property of a human (sex, age, ethnicity, skin tone, build, height,
  face, clothing, landmarks) comes from a distribution or quota in a YAML file. Changing the
  population means editing numbers, not code.
* **Two engines, one contract.** The sampling engine (pure Python) resolves all randomness into
  `manifest.json`. The build engine (Blender + MPFB) only reads that manifest, so a build depends
  on its manifest entry and the asset files alone.
* **Scalable.** Each human is an independent Blender process. Workers run in parallel, a crash
  affects one human only, and `--resume` / `--only` continue or rebuild without resampling.

Details: [01 overview](01_overview.md) · [04 pipeline](04_pipeline.md) ·
[05 body and identity](05_body_and_identity.md).
