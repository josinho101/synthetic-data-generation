"""The Z-Anatomy reference package (assets/zanatomy, built by scripts/build_zanatomy_reference.py).

reference.npz   anatomical rig at rest (bone_names, parent, rest_frames [B,4,4] world, Y along the bone), the S4
                reference skin fitted around it (MakeHuman topology), rig joints with their skin rings, all joints /
                bony landmarks with their owner bone, containment samples, the bone and teeth meshes
maps.json       MakeHuman -> anatomical weight map, spine split, surface landmarks (skin vertices + tissue depth),
                L/R pairs, scale chains
manifest.json   version, provenance, sha256 of the two data files
"""

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np

from ...paths import PROJECT_ROOT

_LOG = logging.getLogger("sdg_humans.skeleton.zanatomy")
FILES = ("reference.npz", "maps.json", "manifest.json")


def resolve_dir(layer_cfg: dict) -> Path:
    path = Path(layer_cfg.get("reference_dir", "assets/zanatomy"))
    return path if path.is_absolute() else PROJECT_ROOT / path


def check(ref_dir: Path) -> tuple:
    """-> (ok, detail): all files present and their sha256 match the manifest."""
    missing = [n for n in FILES if not (ref_dir / n).exists()]
    if missing:
        return False, f"missing {missing} in {ref_dir}: run scripts/build_zanatomy_reference.py"
    manifest = json.loads((ref_dir / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        h = hashlib.sha256((ref_dir / name).read_bytes()).hexdigest()
        if h != digest:
            return False, f"{name} does not match manifest.json (rebuild the reference package)"
    return True, f"{manifest['version']} ({manifest['counts']['bones']} bones, {manifest['counts']['meshes']} meshes)"


class Reference:
    def __init__(self, ref_dir: Path):
        self.dir = ref_dir
        self.manifest = json.loads((ref_dir / "manifest.json").read_text())
        self.maps = json.loads((ref_dir / "maps.json").read_text())
        z = np.load(ref_dir / "reference.npz")
        self.data = {k: z[k] for k in z.files}
        self.names = [str(x) for x in self.data["bone_names"]]
        self.parent = self.data["parent"].astype(int)
        self.frames = self.data["rest_frames"]
        self.mesh_keys = [str(x) for x in self.data["meshes"]]
        self.version = self.manifest["version"]

    def mesh(self, key: str) -> tuple:
        """-> (vertices [N,3] rest world, triangles [M,3], owner bone name)."""
        d = self.data
        return d[f"mesh_{key}_v"].astype(np.float64), d[f"mesh_{key}_f"], str(d[f"mesh_{key}_owner"])


@lru_cache(maxsize=2)
def load(ref_dir: str) -> Reference:
    ref = Reference(Path(ref_dir))
    _LOG.debug(f"Z-Anatomy reference {ref.version} loaded from {ref_dir}")
    return ref
