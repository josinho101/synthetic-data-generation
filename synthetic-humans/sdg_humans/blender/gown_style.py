"""Build-time styling of a fitted hospital gown: patterned fabric, relaxed drape, thickness.

MHCLO fitting re-projects the gown onto each body's surface, so body detail (chest,
navel) comes back. A Smooth modifier relaxes the shell; its strength fades to zero
over the first rings next to the cut edges so hems, sleeves and the waist overlap stay
in place. A Displace modifier then inflates the shell slightly and a Solidify modifier
gives it thickness. All modifiers sit after the Armature modifier and are applied in
the rest pose before USD export.
"""

from collections import deque
from pathlib import Path

import bmesh
import bpy

from . import bake, colors


def _load_pixels(path: Path):
    import numpy as np
    image = bpy.data.images.load(str(path), check_existing=False)
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(image.size[1], image.size[0], 4)
    bpy.data.images.remove(image)
    return pixels


def fabric_texture(asset_dir: Path, color: dict, target: Path) -> Path:
    """Per-human fabric: lerp(base, colour, stripe mask) x weave. pattern 'solid' = all colour,
    except the trim band which always stays the base colour."""
    import numpy as np
    mask = _load_pixels(asset_dir / "stripes_mask.png")[..., 0]
    weave = _load_pixels(asset_dir / "cotton_weave.png")[..., 0]
    if color.get("pattern", "stripes") == "solid":
        rows = np.arange(mask.shape[0])[:, None] / mask.shape[0]
        mask = np.where(rows >= 0.9, 0.0, 1.0) * np.ones_like(mask)
    base = np.array(colors.hex_to_srgb(color.get("base_rgb", "#f4f1ec")), dtype=np.float32)
    tint = np.array(colors.hex_to_srgb(color["rgb"]), dtype=np.float32)
    rgb = (base * (1 - mask[..., None]) + tint * mask[..., None]) * weave[..., None]
    out = bpy.data.images.new(target.stem, width=mask.shape[1], height=mask.shape[0], alpha=False)
    out.pixels[:] = np.dstack([np.clip(rgb, 0, 1), np.ones(mask.shape)]).astype(np.float32).ravel()
    out.filepath_raw = str(target)
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    return target


def _edge_falloff_group(obj, rings: int, name: str = "gown_smooth"):
    """Vertex group: 0 on boundary vertices rising linearly to 1 at `rings` edges away."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    distance = {v.index: 0 for v in bm.verts if v.is_boundary}
    queue = deque(distance)
    bm.verts.ensure_lookup_table()
    while queue:
        index = queue.popleft()
        if distance[index] >= rings:
            continue
        for edge in bm.verts[index].link_edges:
            other = edge.other_vert(bm.verts[index]).index
            if other not in distance:
                distance[other] = distance[index] + 1
                queue.append(other)
    count = len(bm.verts)
    bm.free()
    group = obj.vertex_groups.new(name=name)
    for index in range(count):
        group.add([index], min(1.0, distance.get(index, rings) / float(max(rings, 1))), "REPLACE")
    return group


def smooth_lower_weights(obj, bone_names: set, below_fraction: float, iterations: int) -> int:
    """Diffuse the bone weights over the lower part of the garment (Laplacian, per vertex).

    A skirt bound rigidly to each leg tears apart between the legs when walking; blended
    weights make the hem follow both legs and the pelvis smoothly, like loose fabric."""
    mesh = obj.data
    zs = [v.co.z for v in mesh.vertices]
    z_cut = max(zs) - below_fraction * (max(zs) - min(zs))
    groups = {g.index: g.name for g in obj.vertex_groups if g.name in bone_names}
    weights = [{groups[g.group]: g.weight for g in v.groups if g.group in groups} for v in mesh.vertices]
    neighbours = [[] for _ in mesh.vertices]
    for e in mesh.edges:
        a, b = e.vertices
        neighbours[a].append(b)
        neighbours[b].append(a)
    lower = [v.index for v in mesh.vertices if v.co.z < z_cut and neighbours[v.index]]
    for _ in range(iterations):
        updated = {}
        for i in lower:
            acc = {}
            for k in neighbours[i]:
                for bone, w in weights[k].items():
                    acc[bone] = acc.get(bone, 0.0) + w / len(neighbours[i])
            mixed = {bone: 0.5 * weights[i].get(bone, 0.0) + 0.5 * acc.get(bone, 0.0) for bone in set(acc) | set(weights[i])}
            total = sum(mixed.values()) or 1.0
            updated[i] = {bone: w / total for bone, w in mixed.items() if w / total > 1e-3}
        for i, w in updated.items():
            weights[i] = w
    by_name = {}
    for i in lower:
        for bone, w in weights[i].items():
            group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
            by_name.setdefault(group.name, group)
        for group in by_name.values():
            group.remove([i])
        for bone, w in weights[i].items():
            obj.vertex_groups[bone].add([i], w, "REPLACE")
    return len(lower)


def style_gown(obj, spec: dict, clothing: dict, mhclo_path: Path, textures_dir: Path, bone_names=None,
               color: dict = None, label: str = "gown") -> None:
    """Style a generated garment (hospital gown or office skirt). color defaults to the human's
    gown colour; label names the material / texture (one per slot)."""
    color = color or clothing["gown_colors"][spec["gown_color"]]
    asset_textures = mhclo_path.parent / "textures"
    name = f"{spec['id']}_{'gown' if label == 'full_body' else label}"
    if (asset_textures / "stripes_mask.png").exists():
        tex = fabric_texture(asset_textures, color, textures_dir / f"{name}.png")
        material = bake.simple_material(name, image_path=tex, roughness=0.85)
    else:
        material = bake.simple_material(name, color=colors.hex_to_linear_rgba(color["rgb"]), roughness=0.85)
    bake.replace_materials(obj, material)

    shaping = clothing.get("gown_shaping") or {}
    if bone_names and int(shaping.get("weight_smooth_iterations", 0)) > 0:
        smooth_lower_weights(obj, bone_names, float(shaping.get("weight_smooth_below", 0.6)),
                             int(shaping["weight_smooth_iterations"]))
    if int(shaping.get("smooth_iterations", 0)) > 0:
        smooth = obj.modifiers.new("GownSmooth", "SMOOTH")
        smooth.factor = float(shaping.get("smooth_factor", 0.6))
        smooth.iterations = int(shaping["smooth_iterations"])
        smooth.vertex_group = _edge_falloff_group(obj, int(shaping.get("edge_rings", 3))).name
    if float(shaping.get("inflate_cm", 0.0)) > 0:
        inflate = obj.modifiers.new("GownInflate", "DISPLACE")
        inflate.strength = float(shaping["inflate_cm"]) / 100.0
        inflate.mid_level = 0.0
    thickness = float(clothing.get("gown_thickness_cm", 0.0)) / 100.0
    if thickness > 0:
        solid = obj.modifiers.new("GownThickness", "SOLIDIFY")
        solid.thickness = thickness
        solid.offset = 1.0
