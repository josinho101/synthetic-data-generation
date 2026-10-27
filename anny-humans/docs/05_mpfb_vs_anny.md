# 5. MPFB pipeline vs Anny pipeline

| | MPFB (`mpfb-humans`) | Anny (`anny-humans`) |
|---|---|---|
| Body model | MPFB in headless Blender | Anny (PyTorch), no Blender |
| Mesh / rig | hm08, MPFB default rig 163 bones | identical hm08 mesh and rig (`makehuman`) |
| Age | MPFB macro, linear 25 y = 0.5, 90 y = 1 | Anny's WHO-calibrated mapping; **age range 18–70 configurable** |
| Height | bisection on the height macro | bisection on the height phenotype (+ ≤ 6 % uniform scale) |
| Skin | photo skin baked in Cycles, tone matched; diffuse only | photo skin tone matched + **normal / roughness maps + MDL subsurface** |
| Garment fit | MPFB `add_mhclo_asset` | same MHCLO formula in numpy |
| Clothing | gowns + office clothes | office clothes only (gowns later) |
| Landmarks / frames / bone meshes | 175 + 36, 83 meshes | same rules and counts |
| Animation | `<id>_anim.usda` | none (separate scope) |
| PNGs | preview, skeleton, landmarks | preview only (rendered from the USD) |
| Time per human (this machine) | ~68 s (Blender, Cycles bake; latest run) | ~40 s |
| IDs | `H0001` | `A0001` |

Known differences in shape: Anny's breast targets ignore gender. Males use cup / firmness 0.5, which selects no breast
target (neutral, as in MPFB). Face targets that Anny does not include (e.g. `head-round`) are skipped and listed in
the human's notes.
