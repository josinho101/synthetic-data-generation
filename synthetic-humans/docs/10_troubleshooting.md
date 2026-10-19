# 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `[config] Invalid configuration: … must sum to 100` | percent block does not add up | fix the listed keys; all problems are listed at once |
| `FAIL blender  Blender not found` | wrong `export.blender_bin` | `which blender` and update the path |
| `FAIL mpfb import` | MPFB disabled or not installed for this Blender version | install / enable MPFB in Blender; set `export.mpfb_module` if the module name differs (e.g. legacy `mpfb`) |
| `WARN asset packs cfg missing …` / `WARN asset packs` | MakeHuman asset packs not installed (new machine, new Blender version) | `scripts/check_env.py --setup` (or `run_pipeline.py --install-packs`); without them humans get no hair / shoes and all wear gowns |
| `[packs] … failed: HTTP Error` / `URLError` | no internet / proxy / server down | set `https_proxy`, retry (finished packs are skipped), or download the zips elsewhere and use `install_asset_packs.py --from-dir DIR` |
| `MPFB not found - install the MPFB extension` | MPFB not installed for this Blender version | Blender → Preferences → Get Extensions → MPFB, then rerun |
| `FAIL clothing assets missing …gown_standard.mhclo` | gowns not generated | `scripts/make_gown.py` or `check_env.py --fix` |
| `FAIL landmark anchors … not calibrated` | `null` anchors | `scripts/calibrate_anchors.py --auto` |
| `FAIL output dir … not writable` | permissions / path | change `export.output_root` or use `--output-root` |
| `WARN gpu (bake)` | no CUDA/OptiX device visible | bake runs on CPU (slower, same result) |
| `fit not exact … height_ok False` | target stature outside MPFB's range for that body | widen/narrow `height_cm` min/max; the human is kept, `fit_ok=false` |
| `BMI … outside guard` | extreme somatotype ranges | adjust somatotype macro ranges (05 §5.7) or `bmi_guard` |
| gown shows body detail / skin pokes through | tight fit on extreme bodies | raise `clothing.gown_shaping.inflate_cm` or `smooth_iterations`; raise `gown.yaml looseness_cm` and re-run `make_gown.py` |
| textures missing in Isaac Sim | USD moved without its `textures/` folder | keep `H0001.usd` and `textures/` together (paths are relative) |
| human appears black / untextured in Isaac Sim | renderer not RTX or material not loaded | use RTX – Real-Time; check `validate_usd.py` for missing textures |
| landmark joints missing after retargeting | retargeting tool dropped non-deforming joints | keep the original skeleton, or retarget only the deform hierarchy and re-parent `LM_*` joints |
| worker killed after `timeout_s_per_human` | very slow CPU bake / preview | raise the timeout, set `preview.engines: [BLENDER_WORKBENCH]` |
| `Blender exited … without a result` | Blender crashed (out of memory, GPU driver) | see `logs/humans/<id>.blender.log`; reduce `workers` |
| `WARNING: Could not register preferences class` in Blender logs | harmless MPFB message when enabled headless | ignore |
| `Maximum number of closures exceeded` in Blender logs | harmless EEVEE/Cycles note for MPFB's layered skin | ignore (the skin is baked) |
| a bone pokes through the skin (`<id>.png`) | very thin body region vs. the soft-tissue rule | raise `anatomy.soft_tissue_cm` / `soft_tissue_fraction`; check `<id>_skeleton.png` |
| white patches on head / face / chest / shoes (runs before 2026-10-19) | bone meshes were shifted up by the footwear floor lift (fixed: bone objects now get the armature's parent inverse) | regenerate the humans |
| skin looks too light / too dark | `skin_albedo_lab` L* for that Monk level | lower / raise L* by 2–4 for that level; check `appearance.skin.tone` in `<id>.json` |
| skin looks flat / plastic | `skin.source: layered` or packs missing | install packs (`check_env.py --setup`) and use `source: auto` / `mhmat` |
| ribs missing for a human | chest rays found no wall (unusual body shape) | logged as WARNING per part; adjust `rib_end_angle_deg` |
| gown shows horizontal ripples | MHCLO fit follows the ring structure | raise `clothing.gown_shaping.smooth_iterations` |
| run interrupted | Ctrl+C, reboot | `run_pipeline.py --resume --run-dir <run>` |
