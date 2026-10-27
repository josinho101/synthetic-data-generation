# 3. USD and Isaac Sim

```
/<ID>                               Xform, defaultPrim, kind component, customData anny_human {...}
├── <ID>_rig                        SkelRoot
│   ├── <ID>_rig                    Skeleton: SkelOrigin / root / pelvis_L / ... (375 joints)
│   ├── <ID>/base                   body mesh (≤ 13 380 points, quads, faceVarying st, vertex normals)
│   ├── <ID>_eyes/high_poly         eyes (eye_L / eye_R bones)
│   ├── <ID>_<hair>, <ID>_<eyebrows>, <ID>_<eyelashes>
│   ├── <ID>_<garment asset>/<mesh> doubleSided garments
│   └── bone_<name>/bone_<name>     83 anatomy meshes, purpose = guide
└── _materials/<name>               UsdPreviewSurface (outputs:surface) + OmniSurface MDL (outputs:mdl:surface)
```

- Stage: Z up, metres, the human faces -Y, rest pose = bind pose (A-pose), soles (with shoes) on z = 0.
- Joints: `SkelOrigin` (identity at the origin; Isaac's retargeter needs the hips below a root), then the 163 MPFB rig
  joints (`.`/`-` → `_`), then `LM_*` landmarks and `AN_*` frames (non-deforming, parented to rig bones). Bind
  transforms use Blender bone frames (Y along the bone), like the MPFB export.
- Skinning: every mesh has `jointIndices` / `jointWeights` (≤ 4 influences, normalised) and an identity
  `geomBindTransform`. The body uses Anny's linear-blend weights. Garments and hair blend the weights of their three
  MHCLO reference vertices. Bone meshes are rigid.
- Materials: the **UsdPreviewSurface** has a diffuse texture, a roughness map and a normal map (scale 2, bias -1).
  Hair and lace use `opacityThreshold` 0.5. The **OmniSurface** input names come from Isaac 6.2
  `kit/mdl/core/Base/OmniSurface.mdl`:

| Material | OmniSurface inputs |
|---|---|
| skin | `diffuse_reflection_color_image`, `specular_reflection_roughness_image`, `geometry_normal_image`, `enable_diffuse_transmission`, `subsurface_weight`, `subsurface_transmission_color_image`, `subsurface_scattering_color` (radius ratio R:G:B), `subsurface_scale` (largest radius in m), `specular_reflection_ior` 1.4 |
| cloth | `specular_reflection_weight` 0.35, `specular_retro_reflection_weight` 0.15 (fabric back-scatter) |
| eyes | `coat_weight` 1, `coat_roughness` 0.02 (wet cornea) |
| hair | `specular_reflection_anisotropy` 0.6, opacity cut-out |

Checks done without Isaac: `pipeline/validate.py` (axis, units, one SkelRoot / Skeleton, skinned meshes, ≤ 4
influences, textures present, landmark joints present, head height = stature + footwear) and `tests/test_built_human.py`
(joint layout, every `sdg/configs/retarget_mpfb.yaml` joint present, weights normalised, both material outputs).
The Isaac checks themselves are listed in the README.
