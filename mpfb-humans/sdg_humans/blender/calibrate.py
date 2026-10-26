"""Blender task: propose landmark anchor vertex IDs on the neutral MPFB basemesh.

Because all MPFB humans share one topology, a vertex ID found here marks the same
anatomical point on every generated human. The rules live in sdg_humans/landmark_rules.py
(numpy, shared verbatim with the MHR pipeline); MPFB's joint cubes supply the reference
joint centres (front = -Y, back = +Y, left = +X). They are heuristics: refine in the Blender
UI if needed (docs/06_landmarks.md).
"""

import logging

import numpy as np

from .. import landmark_rules
from . import bootstrap, geometry

_LOG = logging.getLogger("sdg_humans.blender.calibrate")

# landmark_rules reference joint -> MPFB joint cube ("{s}" = l / r)
REF_CUBES = {"hip": "{s}-upper-leg", "knee": "{s}-knee", "ankle": "{s}-ankle", "shoulder": "{s}-shoulder",
             "elbow": "{s}-elbow", "wrist": "{s}-hand", "eye": "{s}-eye", "thumb": "{s}-finger-1-2",
             "pinky": "{s}-finger-5-2", "ball": "{s}-toe-3-1"}


def reference_joints(basemesh, coords) -> dict:
    refs = {}
    for ref, cube in REF_CUBES.items():
        for sfx, s in (("L", "l"), ("R", "r")):
            refs[f"{ref}_{sfx}"] = tuple(geometry.joint_centre(basemesh, coords, f"joint-{cube.format(s=s)}"))
    return refs


def propose_anchors(basemesh) -> dict:
    coords = geometry.evaluated_coords(basemesh)
    body = geometry.group_vertex_indices(basemesh, "body")
    points = np.array([tuple(coords[i]) for i in body])
    local = landmark_rules.propose_anchors(points, reference_joints(basemesh, coords))
    anchors = {name: int(body[i]) for name, i in local.items()}
    for name, idx in anchors.items():
        _LOG.debug(f"anchor {name}: vertex {idx} at {tuple(round(v, 3) for v in coords[idx])}")
    return anchors


def run(args: dict) -> dict:
    ns = bootstrap.mpfb(args.get("mpfb_module", "auto"))
    bootstrap.clear_scene()
    basemesh = ns.HumanService.create_human(mask_helpers=True)
    anchors = propose_anchors(basemesh)
    coords = geometry.evaluated_coords(basemesh)
    positions = {k: [round(v, 4) for v in coords[i]] for k, i in anchors.items()}
    _LOG.info(f"proposed {len(anchors)} anchors on the neutral basemesh")
    return {"status": "ok", "anchors": anchors, "positions": positions}
