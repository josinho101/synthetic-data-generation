"""'zanatomy' skeletal layer: Z-Anatomy bone meshes fitted INTO the finished MPFB human; anatomical rig.

The human (body, skin, clothes, hair, materials) is exactly what the MPFB build made; this layer only fits the
skeleton (fit.py), swaps the rig and the skin weights, and adds the bone meshes (usd_rig.py). Method and
validation: ../zanatomy-humans/spike/REPORT.md (S9). Reference data: assets/zanatomy (reference.py).

The USD skeleton is then Z-Anatomy only (SkelOrigin + 156 anatomical joints): the MPFB rig and, by default, its
LM_ / AN_ landmark joints are gone, so animation / retargeting that drives MPFB joint names does not apply.
"""

import logging

from .. import LayerResult, SkeletonLayer

_LOG = logging.getLogger("sdg_humans.skeleton.zanatomy")


class ZAnatomyLayer(SkeletonLayer):
    name = "zanatomy"
    version = "1"
    needs_body_dump = True
    rig_replaced = True

    def preflight(self) -> tuple:
        try:
            import scipy  # noqa: F401
            import torch  # noqa: F401
        except ImportError as exc:
            return "error", f"zanatomy layer needs torch + scipy ({exc}): pip install -r requirements.txt"
        from .reference import check, resolve_dir
        ok, detail = check(resolve_dir(self.layer_cfg))
        return ("ok" if ok else "error"), detail

    def apply(self, ctx) -> LayerResult:
        import numpy as np
        from pxr import Usd, UsdGeom
        from scipy.spatial import cKDTree

        from ...usd_post import set_anatomy_purpose
        from .fit import fit
        from .reference import load, resolve_dir
        from .usd_rig import rewrite

        ref = load(str(resolve_dir(self.layer_cfg)))
        dump = np.load(ctx.body_dump)
        V, tris = dump["vertices"].astype(np.float64), dump["triangles"]
        bmi = float(dump["bmi"])

        # the closed body (world space, from Blender) must be the exported body: compare in world space, then fit
        # in skeleton space (the SkelRoot carries e.g. the footwear lift; skeleton and meshes sit below it)
        stage = Usd.Stage.Open(str(ctx.usd_path))
        base = next(p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh) and p.GetName() == "base")
        skel = next(p for p in stage.Traverse() if p.GetTypeName() == "Skeleton")
        to_world = lambda prim: np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0)).T  # noqa: E731
        Xb, Xs = to_world(base), to_world(skel)
        P = np.array(UsdGeom.Mesh(base).GetPointsAttr().Get(), dtype=np.float64) @ Xb[:3, :3].T + Xb[:3, 3]
        dist = cKDTree(V).query(P)[0]
        tol_mm = float(self.layer_cfg.get("body_match_tolerance_mm", 1.0))
        if dist.max() * 1e3 > tol_mm:
            raise RuntimeError(f"body dump does not match the USD body (max {dist.max() * 1e3:.2f} mm > {tol_mm} mm)")
        del stage
        Xs_inv = np.linalg.inv(Xs)
        V_skel = V @ Xs_inv[:3, :3].T + Xs_inv[:3, 3]

        result = fit(ref, V_skel, tris, bmi, self.layer_cfg)
        result["points"] = {k: (np.array(p) @ Xs[:3, :3].T + Xs[:3, 3]).tolist() for k, p in result["points"].items()}
        m = result["metrics"]
        _LOG.info(f"{ctx.human_id}: skeleton fit in {m['seconds']}s, landmarks median "
                  f"{m['landmark_residual_mm']['median']} mm, exposed ~{m['bone_exposed_frac_approx']:.3f}")
        lm_cfg = ctx.cfg.get("landmarks") or {}
        prefixes = (lm_cfg.get("bone_prefix", "LM_"), (lm_cfg.get("frames") or {}).get("prefix", "AN_"))
        summary = rewrite(ctx.usd_path, ref, result, self.layer_cfg, prefixes)
        stage = Usd.Stage.Open(str(ctx.usd_path))
        purpose = self.layer_cfg.get("bone_purpose", "guide")
        group = stage.GetPrimAtPath(summary["skeleton_prim"].rsplit("/", 1)[0] + "/ZAnatomy")
        if purpose and purpose != "default" and group:
            UsdGeom.Imageable(group).CreatePurposeAttr().Set(purpose)
        guides = set_anatomy_purpose(stage, purpose)
        stage.GetRootLayer().Save()

        warnings = []
        limit = float(self.layer_cfg.get("warn_exposed_frac", 0.03))
        if m["bone_exposed_frac_approx"] > limit:
            warnings.append(f"skeleton: ~{m['bone_exposed_frac_approx']:.1%} of bone samples outside the skin "
                            f"(> {limit:.0%})")
        anatomy = {"source": "zanatomy", "layer_version": self.version, "reference_version": ref.version,
                   "license": "CC-BY-SA-4.0", "bone_meshes": summary["bone_meshes"],
                   "count": len(summary["bone_meshes"]), "bone_triangles": summary["bone_triangles"],
                   "fit": m, "points_m": result["points"], "points_space": "world (stage)"}
        skeleton = {"rig": "zanatomy_anatomical", "bone_count": summary["joints"],
                    "deform_bone_count": summary["anatomical_joints"],
                    "landmark_joint_count": summary["landmark_joints"], "usd_skeleton_prim": summary["skeleton_prim"]}
        info = {"layer": self.name, "version": self.version, "reference": ref.version,
                "reskinned_meshes": summary["reskinned_meshes"], "removed_bone_prims": summary["removed_bone_prims"],
                "dropped_weight": summary["dropped_weight"], "guide_prims": guides,
                "body_match_max_mm": round(float(dist.max() * 1e3), 4)}
        return LayerResult(anatomy=anatomy, skeleton=skeleton, joint_paths=summary["joint_paths"],
                           warnings=warnings, info=info)
