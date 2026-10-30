# Realistic human libraries for the SDG pipeline

Survey of commercial / free human libraries as possible **skin-mesh sources** for the human pipelines
(`mpfb-humans/`, `anny-humans/`) behind the Z-Anatomy skeletal layer.

Checked against vendor pages on **2026-10-30**. Licenses, prices and trials change often: confirm each one
(ideally with legal) before buying or before the data is used to train a model.

## What the pipeline needs from a library

| Requirement | Why |
|---|---|
| Realistic skin and clothing | RGB realism of the captured SDG frames |
| Rigged, skinned body in a neutral pose (FBX / USD) | The Z-Anatomy skeleton (SkelOrigin + 156 joints) is fitted *into* the human and the rig is swapped (S9 method), so the source skeleton does not have to match ours |
| **Count-based generation** (`count: N` in config) | Each pipeline run must produce N unique humans, not pick from a fixed set |
| Linux, preferably headless | The pipelines and Isaac Sim 6.2 run on Linux |
| Free or trial version | Needed for a spike before buying |
| License allows **synthetic data / ML training** | The rendered frames and annotations train models. Many asset EULAs forbid this |

## Overview

Ratings: ✅ good / yes, ⚠️ partial or unclear, ❌ no. Sample images are hosted by the vendors (not copied into
this repo) and may move; where no public image URL exists, the cell links to the vendor gallery.

"Ease of Z-Anatomy integration" rates how easily the S9 method (fit the Z-Anatomy skeleton into the untouched
human, swap the rig) works on the mesh: one shared topology (one landmark map), neutral A / T pose, clean skin
weights, and clothing as separate meshes (so the skin fit and exposure checks see the real body) make it easy.

| Library | Sample | Skin | Clothing | Count-based generation | Linux | Free / trial | ML / synthetic-data license | Ease of Z-Anatomy integration |
|---|---|---|---|---|---|---|---|---|
| **Human Generator 3D** | <img src="https://www.humgen3d.com/images/mike_render.png" width="1600"> | ✅ Good: procedural PBR skin with age, freckles, tone variation | ⚠️ Partial: outfits auto-fit to body, but small library and mediocre garment quality | ✅ Yes: `HumGen3D` Python API + batch generator | ✅ Yes: Blender add-on, runs headless | ✅ Free trial on email request (limited content, 4K watermark); $68 / $128 lifetime | ⚠️ Unclear: license does not address ML, ask vendor in writing | ✅ Easy: one base topology for all humans (one landmark map), neutral pose, clothes are separate meshes, Blender like `mpfb-humans/` |
| **Character Creator 5** | <img src="https://www.reallusion.com/character-creator/includes/images/default/Businesswear.jpg" width="1600"> | ✅ Very good: SkinGen layers, HD scan-based heads | ✅ Very good: modular garments, 13 businesswear bases, Marvelous Designer import | ⚠️ Partial: RLPy scripting exists, no official API docs | ❌ No: Windows 10 / 11 only | ✅ 30-day free trial (30 s motion export cap) | ❌ Not allowed: EULA prohibits ML / AI training | ✅ Easy: one CC base topology, A-pose, separate garment layers. Export step on Windows |
| **Epic MetaHuman** | [Gallery](https://www.metahuman.com) (no public image without login) | ✅ Best: scan-based faces, subsurface skin, aging | ⚠️ Partial: limited outfit set, more via Marvelous Designer | ✅ Yes: Python + Blueprint API (UE 5.7), parametric body | ✅ Yes: Creator plugin on Linux since UE 5.7 | ✅ Free under UE license (< $1M revenue) | ❌ Not allowed: EULA forbids building / enhancing training databases | ⚠️ Medium: fixed topology, but head / body split meshes with LODs and a complex facial rig; export through UE |
| **Daz3D Genesis 9** | [Gallery](https://www.daz3d.com/genesis-9) | ✅ Very good with paid HD skin packs | ✅ Very good: biggest catalog, auto-fits body shape | ✅ Yes: DAZ Script for random morphs, materials, clothes | ❌ No: Daz Studio is Windows / macOS only | ✅ Free: Daz Studio + G9 base; content is paid | ❌ Restricted: standard EULA limits AI; separate paid **AI Datasets** offering | ✅ Easy-medium: one G9 topology, separate clothing; HD subdivision / geografts need flattening, export via Daz Studio |
| **Renderpeople** | <img src="https://renderpeople.com/wp-content/uploads/rp_images/rp_site_images/renderpeople_free_rigged_people.jpg" width="1600"> | ✅ Photoreal: real photogrammetry scans | ✅ Photoreal but baked into the scan (no swap / removal) | ❌ No: fixed scans, N capped by pool size | ✅ Yes: plain asset files (FBX / OBJ / Blender) | ✅ Free rigged / posed samples, no registration | ⚠️ Free: commercial, some copies NoAI. Paid **ML/CV license** (humandataset.com) | ⚠️ Hard: every scan has its own topology (landmarks per scan), skin fit must go through baked clothing, exposure checks impossible |
| **3DPeople** | [Gallery](https://3dpeople.com) | ✅ Photoreal: scanned people | ✅ Photoreal but baked into the scan | ❌ No: fixed scans | ✅ Yes: plain asset files (FBX / OBJ) | ✅ Free samples | ⚠️ Not verified: check ML terms | ⚠️ Hard: same as Renderpeople (per-scan topology, baked clothing) |
| **AXYZ Metropoly** | <img src="https://secure.axyz-design.com/axyzweb/images/axyz-design-metropoly-background-download.jpg" width="1600"> | ✅ Photoreal: scanned people | ✅ Photoreal but baked into the scan | ❌ No: fixed scans | ✅ Yes: asset files (anima software is Windows only, not needed) | ⚠️ Partial: free static minis; free rigged not confirmed | ⚠️ Not verified: check ML terms | ❌ Very hard for free samples (static posed, must be unposed and skinned); rigged paid models as hard as Renderpeople |
| **Reallusion ActorCore** | <img src="https://actorcore.reallusion.com/static/image/FB_og_actorcore.638b1ef.jpg" width="1600"> | ✅ Good: 4K PBR, scan-based and CC-based characters | ✅ Good but baked per character | ❌ No: fixed characters | ✅ Yes: FBX web download, no CC needed | ✅ Rotating free items (Reallusion account) | ❌ Likely not allowed: Reallusion EULA ML restriction | ⚠️ Medium: CC-based characters share CC topology, scan-based ones do not; clothing baked |
| **Meshcapade (SMPL-X)** | <img src="https://meshcapade.com/images/meta/main.jpg" width="1600"> | ⚠️ Weak: needs our own skin textures | ❌ None: body model only, no clothing | ✅ Yes: parametric shape / height / weight, Python | ✅ Yes: Python library + web portal | ✅ 30-day evaluation (no commercialization) | ✅ Allowed with paid commercial license | ✅ Easiest: fixed parametric topology with joint regressor, same approach as the Anny fit (S8 / S9); but no clothing |
| **Avaturn** | <img src="https://assets.avaturn.me/thumb_8369258dda.jpg" width="1600"> | ⚠️ Medium: realistic face from selfie, body less so | ⚠️ Weak: game-quality clothing | ❌ No: one avatar per selfie | ✅ Yes: web app, GLB export (FBX via converter) | ⚠️ Unclear: conflicting reports (free plan vs. $800/month PRO) | ⚠️ Not verified: check terms | ⚠️ Medium: shared body topology, Mixamo-style rig, but clothing merged into the body mesh |

## Details

### Human Generator 3D (HumGen3D)

| | |
|---|---|
| Type | Blender add-on (Human Generator Ultimate, V4+) |
| Price | $68 Personal, $128 Commercial (lifetime, 1 user), sold via Superhive / Blender Market |
| Free / trial | Free trial on email request: limited content and functions, 4K textures with trial watermark, no credit card |
| License | Add-on code GPL-3.0. Assets / textures royalty-free, may not be shared with unlicensed users. AI / ML use **not addressed**: needs written confirmation |
| Linux | ✅ Runs in Blender, so headless `blender -b -P` works |
| Count-based | ✅ `HumGen3D` Python API (V4+) and batch generator class |
| Rig / export | Own humanoid rig (Rigify-compatible). FBX / glTF / USD through Blender |

| Advantages | Disadvantages |
|---|---|
| Only option on the list that is realistic, count-based, Linux and headless at once | ML / synthetic-data use not stated in the license |
| Python API maps directly onto `count: N` | Clothing library is small; one reviewer calls the garment quality mediocre |
| One base topology, so one landmark map for the Z-Anatomy fit | Procedural Blender shaders must be **baked to textures** for USD / Isaac |
| Cheap one-time license | Particle / curve hair must be converted to mesh cards for USD |
| Close to `mpfb-humans/`, which already uses Blender | Trial textures are watermarked (fine for a pipeline spike, not for data) |

### Reallusion Character Creator 5 (CC5)

| | |
|---|---|
| Price | Paid (bundles vary) |
| Free / trial | ✅ 30-day trial. Trial limit: 30 s motion export |
| License | ❌ Reallusion staff (forum, Nov 2025) confirm the EULA lists "machine learning, AI training, or AI-generated output" as prohibited use |
| Linux | ❌ Windows 10 / 11 only |
| Count-based | ⚠️ RLPy Python scripting is used in practice (for example in NVIDIA's ACE docs), but there are no official public API docs |
| Rig / export | CC skeleton, FBX / USD, free Omniverse connector |

| Advantages | Disadvantages |
|---|---|
| Very realistic skin (SkinGen, HD heads) | **License forbids ML / AI training**, which blocks SDG use |
| Best modular clothing (13 businesswear bases, Marvelous Designer import) | Windows only, GUI app, not headless |
| Morph sliders for height / weight / age, one topology | Scripting API unofficial |
| USD / Omniverse export | Trial limits on export |

### Epic MetaHuman

| | |
|---|---|
| Price | Free under the Unreal Engine license (< $1M revenue, then UE standard terms) |
| Free / trial | ✅ Free |
| License | Usable in other engines / software since June 2025. ❌ The EULA forbids using MetaHuman characters or their rendered output "to build or enhance any database or training" (clause as captured May 2026). Epic said it is working on removing the restriction, so check the current EULA |
| Linux | ✅ MetaHuman Creator plugin available on Linux and macOS (5.7). MetaHuman Animator on Linux still planned |
| Count-based | ✅ Python and Blueprint API (5.7), parametric body |
| Rig / export | MetaHuman skeleton (UE5 Manny-based + facial rig), FBX export |

| Advantages | Disadvantages |
|---|---|
| Best skin and faces available | **EULA forbids training-data use**, which blocks SDG use (unless the clause changes) |
| Free, runs on Linux, scriptable | Limited clothing; better outfits need Marvelous Designer work |
| Parametric body plus fixed topology | Needs Unreal Engine as the authoring host (large install) |

### Daz3D Genesis 9

| | |
|---|---|
| Price | Daz Studio and Genesis 9 base free; skins, clothing and morphs paid |
| Free / trial | ✅ Free base |
| License | ❌ The standard EULA defines and restricts AI use. Daz sells separate **AI Datasets** ("fully licensed, commercially safe"), but pricing is only available on request |
| Linux | ❌ Daz Studio Windows / macOS only. The Diffeomorphic Blender importer runs on Linux but needs a Daz Studio export step |
| Count-based | ✅ DAZ Script (random morphs, materials, clothes, batch export) |
| Rig / export | Genesis 9 skeleton, FBX / USD |

| Advantages | Disadvantages |
|---|---|
| Biggest clothing catalog; clothes fit body shape automatically | Standard content not cleared for AI |
| HD skin packs | Interactive use needs an extra Interactive License |
| Separate AI-dataset product exists | Not on Linux |

### Renderpeople

| | |
|---|---|
| Price | Paid per model or bundle. ML / CV licenses via humandataset.com (35,000+ scans, 5,500+ refined models, rigged A-pose scans in everyday clothing) |
| Free / trial | ✅ Free Rigged People (10–15k quads, 8K textures, skinned skeleton), Posed, Animated and 4D samples, no registration |
| License | Free models: commercial use, same terms as paid models. Some free copies (for example on Sketchfab) carry a **NoAI** notice. For ML use, buy the dedicated ML / CV license |
| Linux | ✅ Asset files (FBX, OBJ, Blender, USD for posed) |
| Count-based | ❌ Fixed scans. A pipeline can only sample N from a pool of M purchased people |

| Advantages | Disadvantages |
|---|---|
| Photoreal skin and clothing | No parametric generation: N is capped by the pool size |
| Clear ML / CV license path (paid) | Clothing baked into the scan: can't swap it, skin exposure can't be controlled |
| Free rigged samples: good realism benchmark for a spike | Each scan has its own topology, so landmarks are needed per scan |
| Pure files, so it works on Linux | Body shape fixed per scan (no height / weight control) |

### 3DPeople

| | |
|---|---|
| Free / trial | Free samples (rigged) |
| License | ⚠️ Not verified. Check for ML use |
| Linux | ✅ Asset files (FBX / OBJ) |
| Count-based | ❌ Fixed scans |

| Advantages | Disadvantages |
|---|---|
| Photoreal scans; a second scan source for testing the adapter | Same baked-clothing and fixed-body limits as Renderpeople |
| Linux-friendly files | License for ML not confirmed |

### AXYZ Metropoly

| | |
|---|---|
| Price | Paid per model (all formats included) |
| Free / trial | ⚠️ Free pack of 3 static "mini" scanned people; free rigged models not confirmed |
| License | ⚠️ Not verified |
| Linux | ✅ Asset files (FBX, Collada). anima crowd software is Windows only (not needed) |
| Count-based | ❌ Fixed scans |

| Advantages | Disadvantages |
|---|---|
| High-quality scans, rigged line available | Free content is probably static, not rigged |
| Blender support | Same scan limits; ML license unknown |

### Reallusion ActorCore

| | |
|---|---|
| Free / trial | ✅ Rotating free characters and motions (Reallusion account) |
| License | Free items are commercial. ❌ The Reallusion ML / AI restriction most likely applies |
| Linux | ✅ FBX web download, no Character Creator needed |
| Count-based | ❌ Fixed characters |

| Advantages | Disadvantages |
|---|---|
| CC-style topology and rig on Linux, 4K PBR | ML use likely prohibited |
| Rigged with facial blendshapes | Small, rotating free selection |

### Meshcapade (SMPL-X commercial)

| | |
|---|---|
| Free / trial | ✅ 30-day evaluation (no commercialization of results) |
| License | ✅ Commercial / R&D licenses available (paid; price on request). SMPL-X itself is academic-only without it |
| Linux | ✅ Python, web portal |
| Count-based | ✅ Parametric (shape, height, weight) |

| Advantages | Disadvantages |
|---|---|
| Parametric like Anny; ML use explicitly licensable | No realistic clothing; skin depends on our own textures |
| Fixed topology, 55-joint skeleton | Paid commercial license |

### Avaturn

| | |
|---|---|
| Free / trial | ⚠️ Reports conflict (free plan vs. paid PRO at $800/month) |
| License | ⚠️ Not verified |
| Linux | ✅ Web app, GLB export (FBX via converter) |
| Count-based | ❌ One avatar per selfie |

| Advantages | Disadvantages |
|---|---|
| Realistic faces from a selfie | Not count-based; game-quality clothing; unclear terms |

## Conclusion

1. **No library meets everything for free.** The license is the deciding filter: **CC5, ActorCore and MetaHuman
   forbid ML / training-data use**, and standard Daz content is restricted.
2. **Best spike candidate: Human Generator 3D (free trial).** It is the only one that is realistic, count-based,
   Linux, headless and cheap. Before buying, get the vendor's written confirmation that generated humans and
   renders may be used for synthetic training data.
3. **Photoreal benchmark: Renderpeople free rigged samples.** Use them to measure the realism gap and to test the
   Z-Anatomy fit on a scan. For production data, the paid ML / CV license is required, and N is capped by the
   pool size.
4. **Licensable alternatives if HumGen3D's license is not OK:** Renderpeople ML / CV license (scans), Daz AI
   Datasets (ask for terms) or Meshcapade commercial (parametric body, but no clothing realism). Otherwise
   improve skin and clothing in the existing Anny / MPFB pipelines.

## Sources

- HumGen3D: [GitHub](https://github.com/OliverJPost/HumGen3D), [API docs](https://publish.obsidian.md/human-generator/API/Overview), [pricing](https://www.humgen3d.com/pricing), [site](https://www.humgen3d.com/)
- Character Creator 5: [download / trial](https://www.reallusion.com/character-creator/download.html), [system requirements](https://kb.reallusion.com/Product/53240/System-Requirements), [EULA / ML forum thread](https://discussions.reallusion.com/t/clarification-of-eula-regarding-machine-learning/15873), [Python API request](https://reallusion.com/FeedBackTracker/Issue/CC-Python-API), [NVIDIA ACE CC4 export](https://docs.nvidia.com/ace/omniverse-renderer-microservice/latest/avatar-customization/reallusion-character-preparation.html)
- MetaHuman: [license](https://www.metahuman.com/en-US/license), [5.7 release](https://www.metahuman.com/releases/metahuman-5-7-is-now-available), [CG Channel, June 2025](https://www.cgchannel.com/2025/06/you-can-now-sell-metahumans-or-use-them-in-unity-or-godot/), [EULA AI clause](https://conductatlas.com/platform/unreal-engine/unreal-engine-eula/provision/CA-P-059499/prohibition-on-using-metahuman-for-ai-database-building/), [UE EULA change log](https://www.unrealengine.com/eula-change-log/unreal), [Epic on lifting AI restriction](https://wnhub.io/news/engines/item-52519)
- Daz3D: [EULA](https://www.daz3d.com/eula), [AI Datasets](https://www.daz3d.com/ai-datasets)
- Renderpeople: [free 3D people](https://renderpeople.com/free-3d-people/), [ML / CV datasets](https://humandataset.com/), [Sketchfab NoAI example](https://sketchfab.com/3d-models/eric-rigged-001-rigged-3d-business-man-a46bc9f67aaa415bb4f3241eef900e7f)
- AXYZ: [Metropoly](https://secure.axyz-design.com/en/metropoly), [free scanned people](https://cgtricks.com/free-3d-scanned-people-axyz-design)
- ActorCore: [site](https://actorcore.reallusion.com/), [CG Channel 2022](https://www.cgchannel.com/?p=121885)
- Meshcapade: [body models / licensing](https://meshcapade.com/assets/body-models), [SMPL-X license](https://smpl-x.is.tue.mpg.de/modellicense.html)
- Avaturn: [docs](https://docs.avaturn.me/docs/what-is-avaturn/), [site](https://avaturn.me)
