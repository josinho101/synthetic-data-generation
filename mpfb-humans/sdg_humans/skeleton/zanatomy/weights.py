"""MakeHuman (MPFB default rig, USD joint names) skin weights -> anatomical rig weights.

Limb, girdle, hand / foot and head bones map 1:1 (maps.json -> weights). The MakeHuman spine and neck chain
(spine05..neck03) is split over the 24 vertebrae: the vertex is projected on the polyline of the fitted vertebra
heads and its spine weight shared by the two nearest vertebrae. Non-deforming joints (SkelOrigin, LM_*, AN_*) carry
no weight. Top 4 influences, normalised.
"""

from collections import defaultdict

import numpy as np

NON_DEFORMING = ("SkelOrigin",)


def anatomical_bone(leaf: str, maps: dict, skip_prefixes=("LM_", "AN_")):
    """Anatomical bone for one MakeHuman joint name (None for non-deforming joints)."""
    if leaf in maps["weights"]:
        return maps["weights"][leaf]
    if leaf in NON_DEFORMING or leaf.startswith(tuple(skip_prefixes)):
        return None
    return maps.get("weights_default", "skull")


def spine_polyline(W: np.ndarray, names: list, maps: dict) -> tuple:
    """(points [n+1,3], vertebra names [n]): fitted vertebra heads, caudal -> cranial (L5 -> C1), plus a point 2 cm
    up the top vertebra."""
    order = [f"vertebra_{v}" for v in maps["spine_order"]]
    top = W[names.index(order[-1])]
    pts = np.array([W[names.index(n)][:3, 3] for n in order] + [top[:3, 3] + top[:3, 1] * 0.02])
    return pts, order


def nearest_vertebra(p: np.ndarray, poly: tuple) -> list:
    """[(vertebra, share), (vertebra, share)] for a point near the spine."""
    pts, order = poly
    best = (1e9, 0, 0.0)
    for k in range(len(pts) - 1):
        a, b = pts[k], pts[k + 1]
        u = float(np.clip((p - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1))
        dist = float(np.linalg.norm(p - (a + u * (b - a))))
        if dist < best[0]:
            best = (dist, k, u)
    c = best[1] + best[2] - 0.5
    i0 = int(np.clip(np.floor(c), 0, len(order) - 1))
    f = float(np.clip(c - i0, 0, 1)) if c >= 0 else 0.0
    return [(order[i0], 1 - f), (order[min(i0 + 1, len(order) - 1)], f)]


def remap(indices: np.ndarray, weights: np.ndarray, leafs: list, points: np.ndarray, maps: dict, poly: tuple,
          joint_index: dict, max_influences: int = 4) -> tuple:
    """indices / weights [V,k] over `leafs` -> ([V,max] anatomical joint indices, [V,max] weights, dropped weight)."""
    split = set(maps["spine_split"])
    out_i = np.zeros((len(indices), max_influences), np.int32)
    out_w = np.zeros((len(indices), max_influences), np.float32)
    dropped = 0.0
    for v in range(len(indices)):
        acc, spine = defaultdict(float), 0.0
        for j, w in zip(indices[v], weights[v]):
            if w <= 0:
                continue
            leaf = leafs[int(j)]
            if leaf in split:
                spine += w
                continue
            bone = anatomical_bone(leaf, maps)
            if bone is None:
                dropped += w
                continue
            acc[bone] += w
        if spine > 0:
            for bone, share in nearest_vertebra(points[v], poly):
                acc[bone] += spine * share
        top = sorted(acc.items(), key=lambda kv: -kv[1])[:max_influences] or [("pelvis", 1.0)]
        total = sum(w for _, w in top)
        for c, (bone, w) in enumerate(top):
            out_i[v, c], out_w[v, c] = joint_index[bone], w / total
    return out_i, out_w, dropped
