"""Blender task: propose landmark anchor vertex IDs on the neutral MPFB basemesh.

Because all MPFB humans share one topology, a vertex ID found here marks the same
anatomical point on every generated human. Rules use MPFB's joint cubes as reference
levels (front = -Y, back = +Y, left = +X). They are heuristics: refine in the Blender UI
if needed (docs/06_landmarks.md).
"""

import logging

from . import bootstrap, geometry

_LOG = logging.getLogger("sdg_humans.blender.calibrate")


class _Body:
    def __init__(self, basemesh):
        self.obj = basemesh
        self.coords = geometry.evaluated_coords(basemesh)
        self.body = geometry.group_vertex_indices(basemesh, "body")
        self.midline = [i for i in self.body if abs(self.coords[i].x) < 0.006]

    def j(self, name):
        return geometry.joint_centre(self.obj, self.coords, f"joint-{name}")

    def pick(self, candidates, key):
        candidates = list(candidates)
        if not candidates:
            raise RuntimeError("no candidate vertices for anchor rule")
        return max(candidates, key=key)

    def near_z(self, indices, z, tol=0.008):
        return [i for i in indices if abs(self.coords[i].z - z) < tol]

    def posterior_midline(self, z):
        back = [i for i in self.midline if self.coords[i].y > 0.0]
        return self.pick(self.near_z(back, z, 0.015), lambda i: self.coords[i].y - abs(self.coords[i].z - z))

    def anterior_midline(self, z):
        front = [i for i in self.midline if self.coords[i].y < 0.0]
        return self.pick(self.near_z(front, z, 0.015), lambda i: -self.coords[i].y - abs(self.coords[i].z - z))

    def side(self, indices, sign):
        return [i for i in indices if self.coords[i].x * sign > 0.0]


def _side_anchors(b: _Body, sign: int, suffix: str, l4_z: float) -> dict:
    c = b.coords
    side = "l" if sign > 0 else "r"
    shoulder, hip = b.j(f"{side}-shoulder"), b.j(f"{side}-upper-leg")
    ears = b.side(geometry.group_vertex_indices(b.obj, "ears"), sign)
    ear_z = sum(c[i].z for i in ears) / len(ears)
    eye = b.side(geometry.group_vertex_indices(b.obj, f"helper-{side}-eye"), sign)
    lateral_eye = max(eye, key=lambda i: c[i].x * sign)
    torso = [i for i in b.body if abs(c[i].x) < abs(hip.x) + 0.11]
    return {
        f"tragus_{suffix}": b.pick(b.near_z(ears, ear_z, 0.012), lambda i: -c[i].y),
        f"outer_canthus_{suffix}": min(b.body, key=lambda i: (c[i] - c[lateral_eye]).length),
        f"acromion_{suffix}": b.pick([i for i in b.body if (c[i] - shoulder).length < 0.09],
                                     lambda i: c[i].z + 0.5 * c[i].x * sign),
        f"asis_{suffix}": b.pick([i for i in b.side(b.near_z(torso, hip.z + 0.075, 0.01), sign)
                                  if abs(abs(c[i].x) - abs(hip.x) * 0.85) < 0.015], lambda i: -c[i].y),
        f"iliac_crest_{suffix}": b.pick(b.side(b.near_z(torso, l4_z), sign), lambda i: c[i].x * sign),
        f"greater_trochanter_{suffix}": b.pick(b.side(b.near_z(torso, hip.z), sign), lambda i: c[i].x * sign),
        f"heel_{suffix}": b.pick([i for i in b.side(b.body, sign) if c[i].z < 0.05], lambda i: c[i].y),
    }


def propose_anchors(basemesh) -> dict:
    b = _Body(basemesh)
    c = b.coords
    neck, head, eye = b.j("neck"), b.j("head"), b.j("l-eye")
    spine1, spine2, spine3, spine4 = (b.j(f"spine-{k}") for k in range(1, 5))
    hip, mouth, clavicle = b.j("l-upper-leg"), b.j("mouth"), b.j("l-clavicle")
    l4_z = (spine3.z + spine4.z) / 2.0
    front_mid = [i for i in b.midline if c[i].y < 0.0]
    anchors = {
        "inion": b.posterior_midline(head.z + 0.01),
        "c7_spinous": b.posterior_midline(neck.z - 0.02),
        "t12_spinous": b.posterior_midline(spine2.z + 0.015),
        "l4_spinous": b.posterior_midline(l4_z),
        "s1_spinous": b.posterior_midline(spine4.z - 0.03),
        "coccyx": b.posterior_midline(hip.z - 0.03),
        "vertex": b.pick(b.midline, lambda i: c[i].z),
        "nasion": b.anterior_midline(eye.z + 0.008),
        "chin": b.pick([i for i in front_mid if neck.z + 0.04 < c[i].z < mouth.z and c[i].y < mouth.y + 0.01],
                       lambda i: -c[i].z),
        "jugular_notch": b.anterior_midline(clavicle.z + 0.01),
        "xiphoid": b.anterior_midline(spine1.z - 0.04),
        "navel": b.pick([i for i in front_mid if spine4.z < c[i].z < spine2.z], lambda i: c[i].y),
    }
    anchors.update(_side_anchors(b, +1, "L", l4_z))
    anchors.update(_side_anchors(b, -1, "R", l4_z))
    for name, idx in anchors.items():
        _LOG.debug(f"anchor {name}: vertex {idx} at {tuple(round(v, 3) for v in c[idx])}")
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
