"""Skeletal layer: which skeleton goes into the human, kept separate from the body / clothing build.

configs/skeleton.yaml -> layer selects one implementation:
  procedural  bones generated in Blender from the MPFB rig (blender/anatomy/, configs/anatomy.yaml); MPFB rig kept
  zanatomy    Z-Anatomy bone meshes fitted INTO the finished body; the rig becomes the anatomical rig
  none        no bone meshes; MPFB rig kept

A layer declares what the build must provide (needs_body_dump, builds_in_blender) and what it changes
(rig_replaced), and does its work on the exported USD in apply(ctx) on the host, after usd_post and before
validation. A new skeleton = one new module registered in LAYERS plus its block in skeleton.yaml.

Stdlib only at import time (also imported inside Blender); heavy dependencies are imported in apply().
"""

import importlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LayerContext:
    human_id: str
    human_dir: Path
    work_dir: Path
    usd_path: Path
    metadata: dict                      # <id>.json as written by the build (read only; apply returns updates)
    cfg: dict                           # the whole pipeline config
    body_dump: Path = None              # work/<id>/skeleton_body.npz when the layer asked for it


@dataclass
class LayerResult:
    anatomy: dict = None                # replaces <id>.json -> anatomy
    skeleton: dict = None               # merged into <id>.json -> skeleton
    joint_paths: dict = field(default_factory=dict)   # old USD joint path -> new (landmark joints)
    warnings: list = field(default_factory=list)
    info: dict = field(default_factory=dict)          # logged + stored in <id>.json -> skeleton_layer


class SkeletonLayer:
    name = "base"
    version = "0"
    builds_in_blender = False           # the Blender build creates the bone meshes (procedural)
    needs_body_dump = False             # the Blender build saves the closed body for apply()
    rig_replaced = False                # the USD rig is no longer the MPFB rig (MPFB-name animation won't apply)

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.layer_cfg = (cfg.get("skeleton") or {}).get(self.name) or {}

    def preflight(self) -> tuple:
        """-> (status ok|warn|error, detail)."""
        return "ok", f"{self.name} layer"

    def apply(self, ctx: LayerContext) -> LayerResult:
        return LayerResult()


LAYERS = {"procedural": "sdg_humans.skeleton.procedural:ProceduralLayer",
          "zanatomy": "sdg_humans.skeleton.zanatomy:ZAnatomyLayer",
          "none": "sdg_humans.skeleton.procedural:NoSkeletonLayer"}


def layer_name(cfg: dict) -> str:
    return str((cfg.get("skeleton") or {}).get("layer", "procedural"))


def get_layer(cfg: dict) -> SkeletonLayer:
    name = layer_name(cfg)
    if name not in LAYERS:
        raise ValueError(f"skeleton.layer: unknown layer '{name}' (known {sorted(LAYERS)})")
    module, cls = LAYERS[name].split(":")
    return getattr(importlib.import_module(module), cls)(cfg)
