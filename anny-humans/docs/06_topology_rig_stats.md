# Anny Topology × Rig Statistics

Mesh and skeleton statistics for each output **topology** and **rig** combination
offered by the Anny model.

**Source:** the local Anny Gradio app (`http://127.0.0.1:7860`), endpoint
`/initialize_model(topology, rig)`, queried 2026-10-27. Every value below is
exactly what the app reported. No numbers were taken from published papers.

## What the columns mean

| Metric | Description |
|---|---|
| **Vertices** | Number of 3D points in the output mesh. It depends only on the **topology**: Anny's body shape is resampled onto that topology's vertex layout. More vertices give finer surface detail but cost more memory and skinning time. |
| **Faces** | Number of polygons that connect the vertices. It also depends only on the topology. For triangle meshes, faces ≈ 2 × vertices. The **makehuman** topology is the exception (more vertices than faces). The usual cause is that MakeHuman's base mesh uses quads and carries helper/proxy vertices (eyes, teeth, tongue, clothing helpers) that few faces reference. |
| **Bones** | Number of joints in the skeleton (**rig**) that drives the mesh. It depends only on the rig. More bones allow finer articulation (fingers, face, twist bones) but need more pose parameters. |
| **Blendshapes** | Number of morph targets (per-vertex offset sets) used to shape the body: global phenotypes (gender, age, muscle, weight, height, proportions) plus local modifiers (arms, cheeks, chin, breasts, and so on). It is **1184 in every combination**, so all of Anny's shape controls work on every topology/rig pair. |
| **Max influencing bones** | The largest number of bones that affect any single vertex through linear blend skinning weights. It depends on **both** the topology and the rig, because the rig's weights are transferred onto the topology's vertices. This matters for export: many real-time engines and formats cap influences at **4** (sometimes 8) per vertex, so any value above that limit is pruned and renormalised on export. Skinning can then deform slightly differently. |

## Full matrix

| Topology | Rig | Vertices | Faces | Bones | Blendshapes | Max influencing bones |
|---|---|---:|---:|---:|---:|---:|
| anny | anny | 13,718 | 27,420 | 104 | 1184 | 9 |
| anny | makehuman | 13,718 | 27,420 | 163 | 1184 | 9 |
| anny | mixamo | 13,718 | 27,420 | 52 | 1184 | 5 |
| anny | soma | 13,718 | 27,420 | 78 | 1184 | 13 |
| smpl | anny | 6,890 | 13,776 | 104 | 1184 | 10 |
| smpl | makehuman | 6,890 | 13,776 | 163 | 1184 | 12 |
| smpl | mixamo | 6,890 | 13,776 | 52 | 1184 | 5 |
| smpl | soma | 6,890 | 13,776 | 78 | 1184 | 13 |
| smplx | anny | 10,475 | 20,908 | 104 | 1184 | 10 |
| smplx | makehuman | 10,475 | 20,908 | 163 | 1184 | 12 |
| smplx | mixamo | 10,475 | 20,908 | 52 | 1184 | 5 |
| smplx | soma | 10,475 | 20,908 | 78 | 1184 | 13 |
| soma | anny | 18,056 | 36,108 | 104 | 1184 | 10 |
| soma | makehuman | 18,056 | 36,108 | 163 | 1184 | 12 |
| soma | mixamo | 18,056 | 36,108 | 52 | 1184 | 5 |
| soma | soma | 18,056 | 36,108 | 78 | 1184 | 14 |
| makehuman | anny | 19,158 | 13,742 | 104 | 1184 | 12 |
| makehuman | makehuman | 19,158 | 13,742 | 163 | 1184 | 12 |
| makehuman | mixamo | 19,158 | 13,742 | 52 | 1184 | 6 |
| makehuman | soma | 19,158 | 13,742 | 78 | 1184 | 13 |

## Per-topology summary (rig-independent)

| Topology | Vertices | Faces | Notes |
|---|---:|---:|---|
| smpl | 6,890 | 13,776 | Lightest mesh; standard SMPL body layout |
| smplx | 10,475 | 20,908 | SMPL-X layout with articulated hands and face |
| anny | 13,718 | 27,420 | Anny's native mesh |
| soma | 18,056 | 36,108 | Densest triangle mesh |
| makehuman | 19,158 | 13,742 | Most vertices, fewest faces (quad base mesh plus helper vertices) |

## Per-rig summary (topology-independent bone count)

| Rig | Bones | Max influencing bones (range across topologies) |
|---|---:|---|
| mixamo | 52 | 5–6 |
| soma | 78 | 13–14 |
| anny | 104 | 9–12 |
| makehuman | 163 | 9–12 |

## Takeaways

- **Vertices and faces** follow from the topology alone. **Bones** follow from the rig alone. **Blendshapes** are always 1184.
- **mixamo** is the most engine-friendly rig: it has the fewest bones (52) and a 5–6 influence maximum, close to the common 4-influence limit.
- **soma** has the highest per-vertex influence counts (13–14) despite a moderate bone count, so it loses the most when pruned to 4 influences.
- **makehuman** has the most bones (163). It is the rig this project uses (see [01_overview.md](01_overview.md)). Its 9–12 influence maximum needs pruning for Isaac Sim and USD consumers that limit influences.
- The native **anny/anny** pairing has the lowest influence maximum (9) among the non-mixamo rigs.

## Reproducing

```bash
curl -s -X POST http://127.0.0.1:7860/gradio_api/call/initialize_model \
     -H 'Content-Type: application/json' -d '{"data":["smplx","mixamo"]}'
# -> {"event_id": "..."}; then
curl -s -N http://127.0.0.1:7860/gradio_api/call/initialize_model/<event_id>
```

The first element of the `complete` event's `data` array holds the statistics as Markdown.
