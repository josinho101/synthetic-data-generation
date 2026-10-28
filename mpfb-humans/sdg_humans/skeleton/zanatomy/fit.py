"""Fit the Z-Anatomy skeleton INTO a finished body (torch). The body is never changed.

Every anatomical bone gets a local rotation, a length scale (bone Y) and a breadth / depth scale (bone X / Z),
bounded around the stature scale; children attach at the parent's scaled point (forward kinematics), so joints stay
connected and every bone keeps its anatomical shape. Losses:
  joint prior   every rig joint where its ring of reference-skin vertices puts it (local similarity reference ring
                -> this body's ring; vertex correspondence = MakeHuman topology)
  landmarks     bony landmark at (skin point - normal x tissue depth); depths scaled with BMI
  containment   bone samples at least their minimum depth inside the skin; ramped in once the skeleton is placed
  symmetry      L/R scales equal;  smoothness: neighbouring vertebrae / ribs scale alike;  small rotations
The best state after the ramp is kept.
"""

import logging
import time

import numpy as np

_LOG = logging.getLogger("sdg_humans.skeleton.zanatomy")


def vertex_normals(V: np.ndarray, tris: np.ndarray) -> np.ndarray:
    a, b, c = V[tris[:, 0]], V[tris[:, 1]], V[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    n = np.zeros_like(V)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _similarity(A: np.ndarray, B: np.ndarray):
    """(s, R, ma, mb) with B ~ mb + s R (A - ma)."""
    ma, mb = A.mean(0), B.mean(0)
    U, Sv, Vt = np.linalg.svd((B - mb).T @ (A - ma))
    D = np.eye(3)
    D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt
    return (Sv * np.diag(D)).sum() / ((A - ma) ** 2).sum(), R, ma, mb


def joint_prior(ref, V: np.ndarray) -> np.ndarray:
    """[J,3] where each rig joint sits in this body, from its ring of reference-skin vertices."""
    skin, rest, rings = ref.data["ref_skin"], ref.data["joint_rest"], ref.data["joint_rings"]
    out = np.zeros_like(rest)
    for i in range(len(rest)):
        ring = rings[i][rings[i] >= 0]
        s, R, ma, mb = _similarity(skin[ring], V[ring])
        out[i] = mb + s * R @ (rest[i] - ma)
    return out


def fit(ref, V: np.ndarray, tris: np.ndarray, bmi: float, cfg: dict) -> dict:
    """Fit the reference skeleton into the body V [13380,3] (MakeHuman topology, closed surface tris).
    -> {W [B,4,4] rigid posed frames, S [B,3] scales, points {name: xyz}, metrics}."""
    import torch
    from scipy.spatial import cKDTree

    torch.set_num_threads(int(cfg.get("threads", 0)) or torch.get_num_threads())
    T = lambda a: torch.as_tensor(np.asarray(a), dtype=torch.float64)          # noqa: E731
    d, maps = ref.data, ref.maps
    names, parent, M = ref.names, ref.parent, ref.frames
    NB = len(names)
    Minv = np.linalg.inv(M)
    N = vertex_normals(V, tris)
    stature = float(V[:, 2].max() - V[:, 2].min())
    g = stature / float(maps["reference_stature_m"])
    soft = float(np.clip(bmi / float(cfg.get("normal_bmi", 23.5)), 0.7, 1.8))
    thin = float(cfg.get("thin_tissue_mm", 8.0))

    def local_of(points, bone_idx):
        p = np.c_[points, np.ones(len(points))]
        return np.einsum("nij,nj->ni", Minv[bone_idx], p)[:, :3]

    # targets
    prior = joint_prior(ref, V)
    jb, ji = d["rig_joint_bone"], d["rig_joint_index"]
    J_local, J_tgt = T(local_of(d["joint_rest"][ji], jb)), T(prior[ji])
    lms = maps["landmarks"]
    LM_bone = np.array([l["bone"] for l in lms])
    LM_local = T(local_of(np.array([l["rest"] for l in lms]), LM_bone))
    tg = []
    for l in lms:
        idx = np.array(l["skin_vertices"])
        n = N[idx].mean(0)
        n /= np.linalg.norm(n)
        t_mm = l["tissue_mm"] * (np.sqrt(soft) if l["tissue_mm"] <= thin else soft)
        tg.append(V[idx].mean(0) - n * t_mm / 1e3)
    LM_tgt = T(np.array(tg))
    sb = d["sample_bone"]
    S_local, need_t = T(local_of(d["sample_points"], sb)), T(d["sample_min_depth_m"])

    # model
    L_rest = np.array([Minv[parent[i]] @ M[i] if parent[i] >= 0 else M[i] for i in range(NB)])
    L_t = T(L_rest)
    rot = torch.zeros(NB, 3, dtype=torch.float64, requires_grad=True)
    a_len = torch.zeros(NB, dtype=torch.float64, requires_grad=True)
    a_brd = torch.zeros(NB, dtype=torch.float64, requires_grad=True)
    trans = torch.zeros(3, dtype=torch.float64, requires_grad=True)
    b_len, b_brd = float(cfg.get("length_bound", 0.25)), float(cfg.get("breadth_bound", 0.40))

    def rotmat(rv):
        th = rv.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        k = rv / th
        K = torch.zeros(rv.shape[0], 3, 3, dtype=rv.dtype)
        K[:, 0, 1], K[:, 0, 2], K[:, 1, 0] = -k[:, 2], k[:, 1], k[:, 2]
        K[:, 1, 2], K[:, 2, 0], K[:, 2, 1] = -k[:, 0], -k[:, 1], k[:, 0]
        s, c = torch.sin(th)[..., None], torch.cos(th)[..., None]
        return torch.eye(3, dtype=rv.dtype) + s * K + (1 - c) * K @ K

    def fk():
        sl = g * torch.exp(b_len * torch.tanh(a_len))
        sbr = g * torch.exp(b_brd * torch.tanh(a_brd))
        S = torch.stack([sbr, sl, sbr], 1)
        R = rotmat(rot)
        W = [None] * NB
        for i in range(NB):                        # parents come first (checked when the package was built)
            L = L_t[i]
            if parent[i] >= 0:
                L = torch.cat([torch.cat([L[:3, :3], (S[parent[i]] * L[:3, 3])[:, None]], 1), L[3:]], 0)
                base = W[parent[i]] @ L
            else:
                base = torch.cat([torch.cat([L[:3, :3], (g * L[:3, 3] + trans)[:, None]], 1), L[3:]], 0)
            Ri = torch.eye(4, dtype=torch.float64)
            Ri[:3, :3] = R[i]
            W[i] = base @ Ri
        return torch.stack(W), S

    def place(W, S, bone_idx, local):
        return torch.einsum("nij,nj->ni", W[bone_idx, :3, :3], local * S[bone_idx]) + W[bone_idx, :3, 3]

    pairs = np.array(maps["lr_pairs"])
    chains = maps["chains"]
    V_t, N_t = T(V), T(N)
    kd = cKDTree(V)
    pelvis = names.index("pelvis")
    with torch.no_grad():                          # start: the pelvis on its prior
        W0, _ = fk()
        head = [k for k in range(len(jb)) if jb[k] == pelvis][0]
        trans += J_tgt[head] - W0[pelvis, :3, 3]

    iters = int(cfg.get("iters", 300))
    lr = cfg.get("lr") or {}
    opt = torch.optim.Adam([{"params": [rot], "lr": lr.get("rotation", 0.02)},
                            {"params": [a_len, a_brd], "lr": lr.get("scale", 0.03)},
                            {"params": [trans], "lr": lr.get("translation", 0.003)}])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=iters, eta_min=0.002)
    w = {"joint": 1.0, "landmarks": 1.0, "containment": 3.0, "symmetry": 50.0, "smoothness": 20.0,
         "rotation": 0.01, "scale": 0.05} | (cfg.get("weights") or {})
    r0, r1 = (cfg.get("contain_ramp") or [100, 150])
    best, t0, nn = (float("inf"), None, -1), time.monotonic(), None
    for it in range(iters):
        W, S = fk()
        L_j = ((place(W, S, jb, J_local) - J_tgt) ** 2).sum(-1).mean() * 1e4
        L_lm = ((place(W, S, LM_bone, LM_local) - LM_tgt) ** 2).sum(-1).mean() * 1e4
        Pb = place(W, S, sb, S_local)
        if it % 20 == 0:
            nn = torch.as_tensor(kd.query(Pb.detach().numpy())[1])
        depth = ((V_t[nn] - Pb) * N_t[nn]).sum(-1)
        L_c = (torch.relu(need_t - depth) ** 2).mean() * 1e5
        L_sym = ((a_len[pairs[:, 0]] - a_len[pairs[:, 1]]) ** 2 + (a_brd[pairs[:, 0]] - a_brd[pairs[:, 1]]) ** 2).mean()
        L_sm = sum(((x[1:] - x[:-1]) ** 2).mean() for ch in chains for x in (a_len[ch], a_brd[ch]))
        ramp = min(1.0, max(0.0, (it - r0) / max(1, r1 - r0)))
        loss = (w["joint"] * L_j + w["landmarks"] * L_lm + ramp * w["containment"] * L_c + w["symmetry"] * L_sym
                + w["smoothness"] * L_sm + w["rotation"] * (rot ** 2).sum()
                + w["scale"] * (torch.tanh(a_len) ** 2 + torch.tanh(a_brd) ** 2).mean())
        if it >= r1 and loss.item() < best[0]:
            best = (loss.item(), [x.detach().clone() for x in (rot, a_len, a_brd, trans)], it)
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
        if it % 50 == 0 or it == iters - 1:
            _LOG.debug(f"fit it {it}: loss {loss.item():.3f} joint {L_j.sqrt().item() * 10:.1f} mm "
                       f"landmarks {L_lm.sqrt().item() * 10:.1f} mm exposed {(depth < 0).double().mean().item():.3f}")
    with torch.no_grad():
        if best[1] is not None:
            for x, v in zip((rot, a_len, a_brd, trans), best[1]):
                x.copy_(v)
        W, S = fk()
        Pb = place(W, S, sb, S_local)
        nn = torch.as_tensor(kd.query(Pb.numpy())[1])
        depth = ((V_t[nn] - Pb) * N_t[nn]).sum(-1).numpy()
        lm_res = np.linalg.norm((place(W, S, LM_bone, LM_local) - LM_tgt).numpy(), axis=1) * 1e3
        j_res = np.linalg.norm((place(W, S, jb, J_local) - J_tgt).numpy(), axis=1) * 1e3
        pb_ = d["point_bone"]
        pts = place(W, S, torch.as_tensor(pb_), T(local_of(d["point_rest"], pb_))).numpy()
    Sn = S.numpy() / g
    metrics = {"iterations": iters, "best_iteration": best[2], "seconds": round(time.monotonic() - t0, 1),
               "stature_scale": round(g, 4), "soft_tissue_factor": round(soft, 3),
               "landmark_residual_mm": {"median": round(float(np.median(lm_res)), 1),
                                        "p90": round(float(np.percentile(lm_res, 90)), 1)},
               "joint_prior_residual_mm": {"median": round(float(np.median(j_res)), 1),
                                           "p90": round(float(np.percentile(j_res, 90)), 1)},
               "bone_exposed_frac_approx": round(float((depth < 0).mean()), 4),
               "too_shallow_frac_approx": round(float((depth < d["sample_min_depth_m"]).mean()), 4),
               "scale_rel_to_stature": {"length": [round(float(x), 3) for x in np.percentile(Sn[:, 1], [0, 50, 100])],
                                        "breadth": [round(float(x), 3) for x in np.percentile(Sn[:, 0], [0, 50, 100])]},
               "lr_scale_diff_max": round(float(np.abs(Sn[pairs[:, 0]] - Sn[pairs[:, 1]]).max()), 4)}
    return {"W": W.numpy(), "S": S.numpy(), "points": {str(n): p.tolist() for n, p in zip(d["point_names"], pts)},
            "metrics": metrics}
