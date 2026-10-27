"""MakeHuman proxy assets (MHCLO: clothes, hair, eyebrows, eyelashes, eyes) fitted to an Anny body without Blender.

Same rule as MPFB's ClothesService.fit_clothes_to_human: every proxy vertex is a weighted sum of three hm08 base
mesh vertices plus an offset scaled by the body's size along x / y / z (distance between two reference vertices
relative to the MHCLO's reference). Anny's rest space equals MPFB's Blender space, so the formula applies as is.
Skin weights are transferred from the three reference vertices (negative barycentric weights ignored).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_LOG = logging.getLogger("anny_humans.proxy_fit")


@dataclass
class Mhclo:
    path: Path
    name: str = ""
    obj_file: Path = None
    material: Path = None
    refs: np.ndarray = None          # [N, 3] base mesh vertex indices
    weights: np.ndarray = None       # [N, 3]
    offsets: np.ndarray = None       # [N, 3] in Blender axes (d0, -d2, d1)
    x_scale: tuple = None
    y_scale: tuple = None
    z_scale: tuple = None
    z_depth: int = 50
    delete_verts: list = field(default_factory=list)


def parse_mhclo(path) -> Mhclo:
    path = Path(path)
    m = Mhclo(path=path, name=path.stem)
    refs, weights, offsets = [], [], []
    status = ""
    with open(path, "r", encoding="utf8", errors="surrogateescape") as handle:
        for line in handle:
            words = line.split()
            if not words:
                status = ""
                continue
            if words[0].startswith("#"):
                continue
            if words[0] == "material":       # may appear inside the verts block (MPFB parses it first, too)
                m.material = path.parent / words[1]
                continue
            if status == "v":
                if not words[0].isnumeric():
                    status = ""
                elif len(words) == 1:
                    v = int(words[0])
                    refs.append((v, v, v))
                    weights.append((1.0, 0.0, 0.0))
                    offsets.append((0.0, 0.0, 0.0))
                    continue
                else:
                    refs.append(tuple(int(w) for w in words[:3]))
                    weights.append(tuple(float(w) for w in words[3:6]))
                    d0, d1, d2 = (float(w) for w in words[6:9])
                    offsets.append((d0, -d2, d1))
                    continue
            elif status == "d":
                if not words[0].isnumeric():
                    status = ""
                else:
                    sequence, previous = False, None
                    for w in words:
                        if w == "-":
                            sequence = True
                            continue
                        v = int(w)
                        if sequence and previous is not None:
                            m.delete_verts.extend(range(previous + 1, v + 1))
                        else:
                            m.delete_verts.append(v)
                        sequence, previous = False, v
                    continue
            key = words[0]
            status = ""
            if key == "obj_file":
                m.obj_file = path.parent / words[1]
            elif key == "name":
                m.name = words[1]
            elif key == "verts":
                status = "v"
            elif key in ("x_scale", "y_scale", "z_scale"):
                setattr(m, key, (int(words[1]), int(words[2]), float(words[3])))
            elif key == "z_depth":
                m.z_depth = int(words[1])
            elif key == "delete_verts":
                status = "d"
    m.refs = np.asarray(refs, dtype=np.int64).reshape(-1, 3)
    m.weights = np.asarray(weights, dtype=np.float64).reshape(-1, 3)
    m.offsets = np.asarray(offsets, dtype=np.float64).reshape(-1, 3)
    if m.material is not None and not m.material.exists():
        alt = m.path.with_suffix(".mhmat")
        m.material = alt if alt.exists() else None
    return m


@dataclass
class ObjMesh:
    vertex_count: int
    faces: list          # [[v, ...], ...]
    uv: np.ndarray       # [K, 2]
    uv_faces: list       # [[t, ...], ...] (same shape as faces; empty lists when there are no UVs)


def parse_obj(path) -> ObjMesh:
    count, uv, faces, uv_faces = 0, [], [], []
    with open(path, "r", encoding="utf8", errors="surrogateescape") as handle:
        for line in handle:
            if line.startswith("v "):
                count += 1
            elif line.startswith("vt "):
                parts = line.split()
                uv.append((float(parts[1]), float(parts[2])))
            elif line.startswith("f "):
                f, t = [], []
                for token in line.split()[1:]:
                    bits = token.split("/")
                    f.append(int(bits[0]) - 1 if int(bits[0]) > 0 else count + int(bits[0]))
                    if len(bits) > 1 and bits[1]:
                        t.append(int(bits[1]) - 1 if int(bits[1]) > 0 else len(uv) + int(bits[1]))
                faces.append(f)
                uv_faces.append(t if len(t) == len(f) else [])
    return ObjMesh(count, faces, np.asarray(uv, dtype=np.float64).reshape(-1, 2), uv_faces)


def parse_mhmat(path) -> dict:
    """Key -> value (strings; texture paths resolved next to the .mhmat)."""
    out = {}
    if path is None or not Path(path).exists():
        return out
    path = Path(path)
    with open(path, "r", encoding="utf8", errors="surrogateescape") as handle:
        for line in handle:
            words = line.split(None, 1)
            if len(words) < 2 or words[0].startswith("#"):
                continue
            key, value = words[0], words[1].strip()
            if key.endswith("Texture"):
                candidate = path.parent / value
                if not candidate.exists():
                    candidate = path.parent / Path(value).name
                out[key] = candidate if candidate.exists() else None
            else:
                out[key] = value
    return out


def mhmat_color(mat: dict, key: str, default=(1.0, 1.0, 1.0)) -> np.ndarray:
    try:
        return np.array([float(v) for v in mat[key].split()[:3]], dtype=np.float64)
    except (KeyError, ValueError):
        return np.array(default, dtype=np.float64)


def fit_points(m: Mhclo, coords) -> np.ndarray:
    """Proxy vertex positions on the body (coords: all hm08 vertices, USD space)."""
    sizes = np.ones(3)
    if m.x_scale and m.y_scale and m.z_scale:
        x = abs(coords[m.x_scale[0], 0] - coords[m.x_scale[1], 0]) / m.x_scale[2]
        y = abs(coords[m.y_scale[0], 2] - coords[m.y_scale[1], 2]) / m.y_scale[2]
        z = abs(coords[m.z_scale[0], 1] - coords[m.z_scale[1], 1]) / m.z_scale[2]
        sizes = np.array([x, z, y])        # MPFB: offset * (x_size, z_size, y_size) in Blender axes
    else:
        sizes *= 0.1                        # MakeHuman decimetres -> metres
    return np.einsum("nk,nkd->nd", m.weights, coords[m.refs]) + m.offsets * sizes


def transfer_weights(m: Mhclo, skin_index, skin_weight, max_influences: int = 4) -> tuple:
    """Bone weights of the reference vertices, blended by the (positive) MHCLO weights -> ([N, k], [N, k])."""
    w = np.clip(m.weights, 0.0, None)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-12)
    idx = skin_index[m.refs].reshape(len(m.refs), -1)                 # [N, 3 * K]
    wt = (skin_weight[m.refs] * w[:, :, None]).reshape(len(m.refs), -1)
    return merge_influences(idx, wt, max_influences)


def merge_influences(idx, wt, k: int) -> tuple:
    """Sum duplicate joint indices per row, keep the k strongest, renormalise."""
    n = len(idx)
    out_i = np.zeros((n, k), dtype=np.int64)
    out_w = np.zeros((n, k), dtype=np.float64)
    for row in range(n):
        acc = {}
        for j, v in zip(idx[row], wt[row]):
            if v > 0:
                acc[int(j)] = acc.get(int(j), 0.0) + float(v)
        top = sorted(acc.items(), key=lambda t: -t[1])[:k]
        total = sum(v for _, v in top) or 1.0
        for c, (j, v) in enumerate(top):
            out_i[row, c], out_w[row, c] = j, v / total
        if not top:
            out_w[row, 0] = 1.0
    return out_i, out_w


@dataclass
class Proxy:
    """A fitted proxy mesh ready for USD."""
    name: str
    points: np.ndarray
    faces: list
    uv: np.ndarray
    uv_faces: list
    joint_index: np.ndarray
    joint_weight: np.ndarray
    mhclo: Mhclo
    material: dict


def load_and_fit(path, coords, skin_index, skin_weight, max_influences: int = 4) -> Proxy:
    m = parse_mhclo(path)
    if m.obj_file is None or not m.obj_file.exists():
        raise FileNotFoundError(f"{path}: obj_file missing")
    obj = parse_obj(m.obj_file)
    if obj.vertex_count != len(m.refs):
        raise ValueError(f"{path}: {len(m.refs)} vertex matches for {obj.vertex_count} obj vertices")
    points = fit_points(m, coords)
    idx, wt = transfer_weights(m, skin_index, skin_weight, max_influences)
    _LOG.debug(f"proxy {m.name}: {len(points)} vertices, {len(obj.faces)} faces")
    return Proxy(Path(path).stem, points, obj.faces, obj.uv, obj.uv_faces, idx, wt, m, parse_mhmat(m.material))
