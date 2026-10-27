"""Body parts (eyes, eyebrows, eyelashes, hair) and clothing from MakeHuman MHCLO assets, fitted without Blender.

Port of the MPFB pipeline's blender/assets.py + garment_fit.py: same slot picking (clothing_match), recolouring,
sock recolour, outer-layer offset and poke-through correction; the office skirt additionally gets the drape
shaping (smoothing, inflate, blended lower-hem weights) so it can sway with both legs later.
"""

import logging
import random
from collections import deque
from pathlib import Path

import numpy as np

from . import clothing_match, textures
from .geometry import MeshBVH, triangulate, vertex_normals
from .paths import CUSTOM_ASSETS_DIR
from .proxy_fit import load_and_fit, mhmat_color, parse_mhmat

_LOG = logging.getLogger("anny_humans.garments")


def candidates(assets_dir, subdir: str) -> list:
    if assets_dir is None:
        return []
    return [{"name": p.stem, "path": str(p), "pack": None}
            for p in sorted(Path(assets_dir, subdir).glob("*/*.mhclo"))]


def _item(proxy, prim: str, material: dict, kind: str, **extra) -> dict:
    return {"prim": prim, "mesh": proxy.name.replace("-", "_"), "points": proxy.points, "faces": proxy.faces,
            "uv": proxy.uv, "uv_faces": proxy.uv_faces, "joint_index": proxy.joint_index,
            "joint_weight": proxy.joint_weight, "material": material, "kind": kind, "proxy": proxy, **extra}


def _diffuse(proxy, max_px: int):
    """Material colour as a texture (diffuse texture x diffuseColor, like MPFB's colour bake) or None."""
    path = proxy.material.get("diffuseTexture")
    if path is None:
        return None
    pixels = textures.load_rgba(path, textures.fit_size(path, max_px))
    pixels[..., :3] *= mhmat_color(proxy.material, "diffuseColor").astype(np.float32)
    return pixels


def _write(pixels, textures_dir: Path, name: str) -> str:
    textures.save_png(pixels, textures_dir / f"{name}.png")
    return f"{name}.png"


def _copy_normal(proxy, textures_dir: Path, name: str):
    path = proxy.material.get("normalmapTexture")
    if path is None:
        return None
    textures.save_png(textures.load_rgba(path), textures_dir / f"{name}_normal.png", alpha=False)
    return f"{name}_normal.png"


# --------------------------------------------------------------------------------------------- body parts
def add_body_parts(body, rest, spec: dict, appearance: dict, assets_dir, textures_dir: Path, report: dict,
                   max_influences: int) -> tuple:
    """-> (mesh items, used names) for eyes, eyebrows, eyelashes and hair."""
    hid, items, used = spec["id"], [], {}
    coords, si, sw = rest.vertices, body.skin_index, body.skin_weight
    eye_assets = candidates(assets_dir, "eyes") if appearance["eyes"].get("source", "pack") == "pack" else []
    eye_asset = next((c for c in eye_assets if c["name"] == "high-poly"), eye_assets[0] if eye_assets else None)
    if eye_asset:
        proxy = load_and_fit(eye_asset["path"], coords, si, sw, max_influences)
        color = spec["eyes"]["color"]
        material_name = (appearance["eyes"].get("pack_materials") or {}).get(color, "brown")
        mat = parse_mhmat(Path(assets_dir, "eyes", "materials", f"{material_name}.mhmat"))
        texture = None
        if mat.get("diffuseTexture"):
            texture = _write(textures.load_rgba(mat["diffuseTexture"]), textures_dir, f"{hid}_eyes")
        items.append(_item(proxy, f"{hid}_eyes", {"name": f"{hid}_eyes", "kind": "eye", "diffuse": texture,
                                                  "color": [0.8, 0.8, 0.8], "roughness": 0.05}, "eyes"))
        used["eyes"] = f"{eye_asset['name']} ({material_name})"
    else:
        items += generated_eyes(body, rest, spec, appearance)
        used["eyes"] = "generated"
    hair_rgb = textures.hex_to_srgb((appearance.get("hair") or {}).get("rgb", {}).get(spec["hair"]["color"], "#3b2619"))
    wanted = {"eyebrows": spec.get("eyebrows"), "eyelashes": spec.get("eyelashes"),
              "hair": None if spec["hair"]["style"] == "none" else spec["hair"]["style"]}
    for part, name in wanted.items():
        if not name:
            used[part] = None
            continue
        installed = candidates(assets_dir, part)
        match = next((c for c in installed if name.lower() in c["name"].lower()), None)
        if match is None:
            message = f"{part} '{name}' skipped: " + ("not found in installed assets" if installed
                                                      else "no MakeHuman asset pack installed")
            report["warnings" if installed else "notes"].append(message)
            used[part] = None
            continue
        proxy = load_and_fit(match["path"], coords, si, sw, max_influences)
        pixels = _diffuse(proxy, 2048)
        label = f"{hid}_{part}"
        if pixels is not None and part in ("hair", "eyebrows"):
            pixels = textures.tint(pixels, hair_rgb)
        material = {"name": label, "kind": "hair", "diffuse": _write(pixels, textures_dir, label) if pixels is not None
                    else None, "color": [float(c) for c in textures.srgb_to_linear(hair_rgb)], "roughness": 0.5,
                    "normal": _copy_normal(proxy, textures_dir, label), "opacity_cutout": True}
        items.append(_item(proxy, f"{hid}_{match['name']}", material, part))
        used[part] = match["name"]
    _LOG.info(f"body parts: {used}")
    return items, used


def generated_eyes(body, rest, spec: dict, appearance: dict) -> list:
    """Fallback without the eye pack: the base mesh's eye helpers, coloured sclera / iris / pupil per face."""
    iris = textures.srgb_to_linear(textures.hex_to_srgb(appearance["eyes"]["rgb"].get(spec["eyes"]["color"], "#5b3a1e")))
    out = []
    for side, group in (("L", "helper-l-eye"), ("R", "helper-r-eye")):
        verts = body.groups[group]
        keep = np.isin(body.faces, verts) | (body.faces < 0)
        faces = body.faces[keep.all(1)]
        remap = {int(v): k for k, v in enumerate(verts)}
        polys = [[remap[int(v)] for v in f if v >= 0] for f in faces]
        points = rest.vertices[verts]
        centre = points.mean(0)
        colors = []
        for f in polys:
            d = points[f].mean(0) - centre
            cos = float(-d[1] / max(np.linalg.norm(d), 1e-9))
            colors.append([0.003] * 3 if cos > 0.974 else (list(iris) if cos > 0.848 else [0.83, 0.81, 0.77]))
        bone = body.bone_labels.index(f"eye.{side}") if f"eye.{side}" in body.bone_labels else body.bone_labels.index("head")
        n = len(points)
        out.append({"prim": f"{spec['id']}_eye_{side}", "mesh": f"{spec['id']}_eye_{side}", "points": points,
                    "faces": polys, "uv": None, "uv_faces": None,
                    "joint_index": np.full((n, 1), bone), "joint_weight": np.ones((n, 1)),
                    "face_colors": np.array(colors), "kind": "eyes",
                    "material": {"name": f"{spec['id']}_eyes", "kind": "vertex_color", "roughness": 0.1}})
    return out


# --------------------------------------------------------------------------------------------- clothing
def _pick_color(clothing: dict, palette: str, rng):
    entries = clothing["garment_colors"][palette]
    name = rng.choices(list(entries), weights=[float(e["pct"]) for e in entries.values()], k=1)[0]
    return name, entries[name]["rgb"]


def _sock(pixels, path, spec: dict, clothing: dict, rng):
    cfg = clothing.get("sock_recolor") or {}
    if Path(path).stem not in (cfg.get("assets") or []):
        return pixels
    weights = cfg["colors"][spec["sex"]]
    name = rng.choices(list(weights), weights=[float(v) for v in weights.values()], k=1)[0]
    if name == "nude":
        r, g, b = textures.hex_to_srgb(spec["skin"].get("albedo_hex") or spec["skin"]["rgb_hex"])
        rgb = (r * 0.8, g * 0.75, b * 0.72)
    else:
        rgb = textures.hex_to_srgb(cfg["rgb"][name])
    pixels, changed = textures.recolor_neutral(pixels, rgb, float(cfg.get("max_saturation", 0.15)),
                                               float(cfg.get("min_value", 0.55)))
    _LOG.info(f"sock of {Path(path).stem}: {name} ({changed} texture pixels)")
    return pixels


def _neighbours(n: int, faces) -> list:
    nb = [set() for _ in range(n)]
    for f in faces:
        for a in range(len(f)):
            i, j = f[a], f[(a + 1) % len(f)]
            nb[i].add(j)
            nb[j].add(i)
    return [sorted(s) for s in nb]


def _boundary_distance(n: int, faces, rings: int) -> np.ndarray:
    """Edge rings from the open boundary (0 on boundary vertices), capped at rings."""
    edges = {}
    for f in faces:
        for a in range(len(f)):
            key = tuple(sorted((f[a], f[(a + 1) % len(f)])))
            edges[key] = edges.get(key, 0) + 1
    dist = np.full(n, rings, dtype=np.int64)
    queue = deque()
    for (i, j), count in edges.items():
        if count == 1:
            for v in (i, j):
                if dist[v] != 0:
                    dist[v] = 0
                    queue.append(v)
    nb = _neighbours(n, faces)
    while queue:
        v = queue.popleft()
        for w in nb[v]:
            if dist[v] + 1 < dist[w]:
                dist[w] = dist[v] + 1
                queue.append(w)
    return dist


def shape_skirt(item: dict, shaping: dict, max_influences: int) -> None:
    """Relax the fitted skirt (Laplacian smoothing fading out at the waist / hem, small inflate) and blend the skin
    weights over its lower part (hem follows both legs and the pelvis smoothly)."""
    points, faces = item["points"].copy(), item["faces"]
    n = len(points)
    nb = _neighbours(n, faces)
    iterations = int(shaping.get("smooth_iterations", 0))
    if iterations:
        rings = int(shaping.get("edge_rings", 3))
        falloff = np.minimum(1.0, _boundary_distance(n, faces, rings) / float(max(rings, 1)))
        factor = float(shaping.get("smooth_factor", 0.5)) * falloff
        for _ in range(iterations):
            mean = np.array([points[k].mean(0) if k else p for p, k in zip(points, nb)])
            points += (mean - points) * factor[:, None]
    inflate = float(shaping.get("inflate_cm", 0.0)) / 100.0
    if inflate > 0:
        points += vertex_normals(points, triangulate(faces)) * inflate
    item["points"] = points
    w_iter = int(shaping.get("weight_smooth_iterations", 0))
    if w_iter:
        z = points[:, 2]
        lower = np.where(z < z.max() - float(shaping.get("weight_smooth_below", 0.6)) * np.ptp(z))[0]
        dense = {}
        for v in range(n):
            dense[v] = {int(j): float(w) for j, w in zip(item["joint_index"][v], item["joint_weight"][v]) if w > 0}
        for _ in range(w_iter):
            updated = {}
            for i in lower:
                if not nb[i]:
                    continue
                acc = {}
                for k in nb[i]:
                    for j, w in dense[k].items():
                        acc[j] = acc.get(j, 0.0) + w / len(nb[i])
                mixed = {j: 0.5 * dense[i].get(j, 0.0) + 0.5 * acc.get(j, 0.0) for j in set(acc) | set(dense[i])}
                total = sum(mixed.values()) or 1.0
                updated[i] = {j: w / total for j, w in mixed.items() if w / total > 1e-3}
            dense.update(updated)
        idx = np.zeros((n, max_influences), dtype=np.int64)
        wt = np.zeros((n, max_influences))
        for v in range(n):
            top = sorted(dense[v].items(), key=lambda t: -t[1])[:max_influences] or [(0, 1.0)]
            total = sum(w for _, w in top)
            for c, (j, w) in enumerate(top):
                idx[v, c], wt[v, c] = j, w / total
        item["joint_index"], item["joint_weight"] = idx, wt
    _LOG.info(f"skirt shaped: {iterations} smoothing iterations, inflate {inflate * 100:.1f}cm, "
              f"{w_iter} weight-blend iterations")


def _layer(worn: list, offset_m: float) -> None:
    """Trousers / skirts go over tucked shirts, otherwise the top goes over the bottom (outward offset)."""
    by_slot = {w["slot"]: w for w in worn}
    top, bottom = by_slot.get("upper_body"), by_slot.get("lower_body")
    if not top or not bottom or offset_m <= 0:
        return
    tucked = "tucked" in top["asset"] and "untucked" not in top["asset"]
    outer = bottom if tucked else top
    outer["layer"] = "outer"
    outer["item"]["points"] = outer["item"]["points"] + vertex_normals(
        outer["item"]["points"], triangulate(outer["item"]["faces"])) * offset_m
    _LOG.info(f"layering: {outer['asset']} is the outer garment")


def push_out(points, bvh: MeshBVH, clearance_m: float, max_dist_m: float = 0.06) -> tuple:
    """Move vertices within clearance of (or inside) the skin to clearance outside it."""
    loc, normal, signed, dist = bvh.signed_distance_out(points)
    move = (dist <= max_dist_m) & (signed < clearance_m)
    points = points.copy()
    points[move] = loc[move] + normal[move] * clearance_m
    return points, int(move.sum())


def resolve_poke_through(body_bvh: MeshBVH, worn: list, clothing: dict) -> None:
    clearance = float(clothing.get("poke_through_clearance_cm", 0.3)) / 100.0
    if clearance <= 0:
        return
    offset = float(clothing.get("layer_offset_cm", 0.5)) / 100.0
    skip = set(clothing.get("hide_body_under") or [])
    for entry in sorted(worn, key=lambda w: w.get("layer") == "outer"):   # inner garments first
        if entry["slot"] in skip:
            continue
        extra = offset if entry.get("layer") == "outer" else 0.0
        entry["item"]["points"], moved = push_out(entry["item"]["points"], body_bvh, clearance + extra)
        entry["poke_through_fixed_vertices"] = moved
        _LOG.info(f"poke-through: {entry['asset']} {moved} vertices pushed out of the body")


def add_clothing(body, rest, spec: dict, clothing: dict, assets_dir, textures_dir: Path, report: dict,
                 max_influences: int, variant_name: str = None) -> tuple:
    """Dress the human with its clothing variant (fallback_variant if nothing fits). -> (mesh items, metadata)."""
    variant_name = variant_name or spec["clothing_variant"]
    variant = clothing["variants"][variant_name]
    rng = random.Random(spec["seed"] ^ 0xC10)
    taken, worn, pool = set(), [], None
    hid = spec["id"]
    for slot_name, configured in variant["slots"].items():
        slot = clothing_match.resolve_slot(configured, spec["sex"], rng)
        if slot is None:      # e.g. a female-only garment for a male human
            continue
        if "asset" in slot:
            p = Path(slot["asset"])
            p = p if p.is_absolute() else CUSTOM_ASSETS_DIR / p
            path = p if p.exists() else None
            missing = f"{slot_name}: asset {p} not found"
        else:
            pool = pool if pool is not None else candidates(assets_dir, "clothes")
            choice = clothing_match.pick(pool, slot["mpfb_slot"], spec["sex"], rng, clothing.get("mpfb_packs"), taken)
            path = Path(choice["path"]) if choice else None
            missing = f"{slot_name}: no installed clothes asset matches {slot['mpfb_slot']} (or chance roll)"
        if path is None:
            if clothing.get("fallback_if_missing") == "error" and "asset" in slot:
                raise FileNotFoundError(missing)
            report["warnings" if "asset" in slot else "notes"].append(missing)
            continue
        proxy = load_and_fit(path, rest.vertices, body.skin_index, body.skin_weight, max_influences)
        taken.add(str(path))
        label = f"{hid}_{slot_name}"
        color_name, rgb = (None, None)
        if slot.get("recolor"):
            color_name, rgb = _pick_color(clothing, slot["recolor"], rng)
        pixels = _diffuse(proxy, int(clothing.get("garment_texture_max_px", 1024)))
        weave = path.parent / "textures" / "cotton_weave.png"
        if (pixels is None or "hospital_gown" in str(path)) and weave.exists():   # generated garments (office skirt)
            pixels = textures.fabric(weave, textures.hex_to_srgb(rgb or "#45474b"))
        elif pixels is not None:
            pixels = _sock(pixels, path, spec, clothing, rng)
            if rgb:
                pixels = textures.recolor_garment(pixels, textures.hex_to_srgb(rgb))
        material = {"name": label, "kind": "cloth", "roughness": 0.8 if "hospital_gown" in str(path) else 0.65,
                    "diffuse": _write(pixels, textures_dir, label) if pixels is not None else None,
                    "color": [0.5, 0.5, 0.5], "normal": _copy_normal(proxy, textures_dir, label),
                    "opacity_cutout": bool(pixels is not None and float(pixels[..., 3].min()) < 0.5)}
        item = _item(proxy, f"{hid}_{path.stem}", material, "garment", double_sided=True)
        if "skirt" in path.stem:
            shape_skirt(item, clothing.get("skirt_shaping") or {}, max_influences)
        worn.append({"slot": slot_name, "asset": path.stem, "object": item["prim"], "variant": variant_name,
                     "color": color_name, "delete_verts": len(proxy.mhclo.delete_verts),
                     "hides_body": slot_name in (clothing.get("hide_body_under") or []), "item": item})
        _LOG.info(f"clothing {slot_name}: {path.stem}{f' ({color_name})' if color_name else ''}")
    _layer(worn, float(clothing.get("layer_offset_cm", 0.5)) / 100.0)
    resolve_poke_through(MeshBVH(rest.vertices, body.triangles(body.body_faces)), worn, clothing)
    fallback = clothing.get("fallback_variant")
    if not worn and fallback and fallback != variant_name:
        report["notes"].append(f"clothing variant '{variant_name}' produced no garments; using '{fallback}'")
        return add_clothing(body, rest, spec, clothing, assets_dir, textures_dir, report, max_influences, fallback)
    return [w["item"] for w in worn], [{k: v for k, v in w.items() if k != "item"} for w in worn]


def hide_body_under(body, rest, items: list, meta: list) -> np.ndarray:
    """Body vertices of the delete groups of `hides_body` garments (shoes) that are really inside the garment
    (rays in four horizontal directions and downwards all hit it) -> removed from the exported body."""
    doomed = set()
    directions = np.array([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, -1)], dtype=np.float64)
    for item, info in zip(items, meta):
        if not info.get("hides_body"):
            continue
        group = np.array(sorted(set(item["proxy"].mhclo.delete_verts) & set(body.body_vertices.tolist())))
        if not len(group):
            continue
        cover = MeshBVH(item["points"], triangulate(item["faces"]))
        origins = rest.vertices[group]
        inside = np.ones(len(group), dtype=bool)
        for d in directions:
            inside &= cover.hits_any(origins, np.repeat(d[None], len(group), 0), 0.4)
        doomed.update(int(v) for v in group[inside])
        info["hidden_body_vertices"] = int(inside.sum())
    return np.array(sorted(doomed), dtype=np.int64)
