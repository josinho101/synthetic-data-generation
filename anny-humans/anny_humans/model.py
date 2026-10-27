"""The Anny body model (NAVER LABS Europe) as used by this pipeline.

Anny with rig "makehuman" and topology "makehuman" is the MakeHuman hm08 base mesh (19158 vertices, helpers
included) with the MPFB default rig (163 bones). Its rest space is already the USD convention of the MPFB pipeline:
metres, Z up, front -Y, subject's left +X (= hm08 obj / 10 with axes (x, -z, y), exactly MPFB's Blender space), so
vertex IDs, MHCLO fitting and landmark rules carry over unchanged.
"""

import json
import logging
import re
import threading
from dataclasses import dataclass

import numpy as np

_LOG = logging.getLogger("anny_humans.model")

BODY_GROUP = "body"
PHENOTYPES = ("gender", "age", "muscle", "weight", "height", "proportions", "cupsize", "firmness",
              "african", "asian", "caucasian")


def usd_name(name: str) -> str:
    """Blender-style USD name of a bone ('upperarm01.L' -> 'upperarm01_L', 'toe1-1.L' -> 'toe1_1_L')."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return f"_{name}" if name[:1].isdigit() else name


def _ranges_to_indices(ranges) -> np.ndarray:
    return np.concatenate([np.arange(a, b + 1) for a, b in ranges]) if ranges else np.zeros(0, dtype=np.int64)


@dataclass
class Rest:
    """One evaluated rest body (numpy, USD space)."""
    vertices: np.ndarray      # [V, 3] all hm08 vertices (helpers included)
    heads: np.ndarray         # [J, 3] bone heads
    tails: np.ndarray         # [J, 3] bone tails
    world: np.ndarray         # [J, 4, 4] bone world matrices (column convention, Blender bone frames)

    def translated(self, offset) -> "Rest":
        offset = np.asarray(offset, dtype=np.float64)
        world = self.world.copy()
        world[:, :3, 3] += offset
        return Rest(self.vertices + offset, self.heads + offset, self.tails + offset, world)

    def scaled(self, factor: float, origin) -> "Rest":
        origin = np.asarray(origin, dtype=np.float64)
        world = self.world.copy()
        world[:, :3, 3] = origin + (world[:, :3, 3] - origin) * factor
        return Rest(origin + (self.vertices - origin) * factor, origin + (self.heads - origin) * factor,
                    origin + (self.tails - origin) * factor, world)


class AnnyBody:
    """Loads Anny once; evaluate() is thread-safe (one forward pass at a time)."""

    def __init__(self, body_cfg: dict, device: str = "auto"):
        import torch
        import anny
        from anny.paths import get_anny_root_dir

        self._torch = torch
        self._lock = threading.Lock()
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.version = getattr(anny, "__version__", "unknown")
        self.rig = body_cfg.get("rig", "makehuman")
        self.topology = body_cfg.get("topology", "makehuman")
        model = anny.Anny(rig=self.rig, topology=self.topology, local_changes=body_cfg.get("local_changes", "all"),
                          phenotypes="all")
        self.model = model.to(dtype=torch.float64, device=device).eval()
        self.data_dir = get_anny_root_dir() / "data" / "mpfb2"

        self.bone_labels = list(model.bone_labels)
        self.bone_parents = [int(p) for p in model.bone_parents]
        self.joint_names = [usd_name(b) for b in self.bone_labels]
        self.faces = model.faces.detach().cpu().numpy().astype(np.int64)
        self.uv = model.texture_coordinates.detach().cpu().numpy().astype(np.float64)
        self.uv_faces = model.face_texture_coordinate_indices.detach().cpu().numpy().astype(np.int64)
        self.skin_index = model.vertex_bone_indices.detach().cpu().numpy().astype(np.int64)
        self.skin_weight = model.vertex_bone_weights.detach().cpu().numpy().astype(np.float64)
        self.vertex_count = int(model.template_vertices.shape[0])
        self.phenotype_labels = list(model.phenotype_labels)
        self.local_change_labels = set(model.local_change_labels)
        groups = json.loads((self.data_dir / "mesh_metadata" / "basemesh_vertex_groups.json").read_text())
        self.groups = {name: _ranges_to_indices(r) for name, r in groups.items()}
        self.body_vertices = self.groups[BODY_GROUP]
        body = np.zeros(self.vertex_count, dtype=bool)
        body[self.body_vertices] = True
        self.body_mask = body
        valid = self.faces >= 0
        self.body_faces = np.where((valid & body[np.clip(self.faces, 0, None)] | ~valid).all(1)
                                   & valid[:, :3].all(1))[0]
        _LOG.info(f"Anny {self.version} loaded: rig={self.rig} ({len(self.bone_labels)} bones) "
                  f"topology={self.topology} ({self.vertex_count} vertices, {len(self.body_vertices)} body, "
                  f"{len(self.local_change_labels)} local changes) on {device}")

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, phenotypes: dict, local_changes: dict = None) -> Rest:
        torch = self._torch
        unknown = set(phenotypes) - set(self.phenotype_labels)
        if unknown:
            raise KeyError(f"unknown Anny phenotypes {sorted(unknown)}")
        lc = {k: float(v) for k, v in (local_changes or {}).items() if k in self.local_change_labels}
        with self._lock, torch.no_grad():
            kw = {k: torch.tensor([float(v)], dtype=torch.float64, device=self.device) for k, v in phenotypes.items()}
            lc_kw = {k: torch.tensor([v], dtype=torch.float64, device=self.device) for k, v in lc.items()}
            _pose, phen, local, facial = self.model.get_tensor_inputs(None, kw, lc_kw or None, None)
            coeffs = self.model._get_phenotype_blendshape_coefficients(phen, local, facial)
            rest = self.model.get_rest_model(coeffs)
            out = {k: v[0].detach().cpu().numpy().astype(np.float64) for k, v in rest.items()}
        tails = out.get("rest_bone_tails")
        if tails is None:   # non-Blender orientations: tail along the bone's Y axis
            tails = out["rest_bone_heads"] + out["rest_bone_poses"][:, :3, 1] * 0.05
        return Rest(out["rest_vertices"], out["rest_bone_heads"], tails, out["rest_bone_poses"])

    # ------------------------------------------------------------------ helpers
    def face_target_changes(self, face_targets: list, catalogue: dict) -> tuple:
        """MPFB target picks [{target, value}] -> Anny local changes {label: signed value}, plus skipped names.

        An Anny local change is the positive target of a category ("nose-flaring-incr"); its opposite target
        ("nose-flaring-decr") is the same local change with a negative value."""
        signed = {}
        for categories in catalogue.values():
            for cat in categories:
                opp = cat.get("opposites") or {}
                for side in ("unsided", "left", "right"):
                    pos, neg = opp.get(f"positive-{side}"), opp.get(f"negative-{side}")
                    if pos:
                        signed[pos] = (pos, 1.0)
                    if neg and pos:
                        signed[neg] = (pos, -1.0)
                if not any(opp.values()):
                    for name in cat.get("targets") or []:
                        signed[name] = (name, 1.0)
        changes, skipped = {}, []
        for item in face_targets:
            label, sign = signed.get(item["target"], (item["target"], 1.0))
            if label not in self.local_change_labels:
                skipped.append(item["target"])
                continue
            changes[label] = max(-1.0, min(1.0, changes.get(label, 0.0) + sign * float(item["value"])))
        return changes, skipped

    def triangles(self, face_ids=None) -> np.ndarray:
        """Quads (and triangles padded with -1) of the given faces split into triangles."""
        faces = self.faces if face_ids is None else self.faces[face_ids]
        tris = [faces[:, [0, 1, 2]]]
        quad = faces[:, 3] >= 0 if faces.shape[1] > 3 else np.zeros(len(faces), dtype=bool)
        if quad.any():
            tris.append(faces[quad][:, [0, 2, 3]])
        return np.concatenate(tris)

    def dominant_bones(self) -> np.ndarray:
        """[V] index of the strongest bone per vertex."""
        best = np.argmax(self.skin_weight, axis=1)
        return self.skin_index[np.arange(self.vertex_count), best]
