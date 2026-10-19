"""Create the MPFB basemesh with the sampled macros and face detail targets."""

import logging

_LOG = logging.getLogger("sdg_humans.blender.body")


def macro_dict(spec: dict) -> dict:
    m = spec["macros"]
    return {key: float(m[key]) for key in ("gender", "age", "muscle", "weight", "proportions",
                                           "height", "cupsize", "firmness")} | {"race": dict(m["race"])}


def create_body(ns, spec: dict):
    """Basemesh in meters (scale 0.1), feet on the ground, helpers masked."""
    basemesh = ns.HumanService.create_human(
        mask_helpers=True, detailed_helpers=True, extra_vertex_groups=True,
        feet_on_ground=True, scale=0.1, macro_detail_dict=macro_dict(spec))
    basemesh.name = spec["id"]
    _LOG.info(f"basemesh created with macros {macro_dict(spec)}")
    return basemesh


def apply_face_targets(ns, basemesh, face_targets: list) -> int:
    """Load the face detail targets sampled in stage 1 (MPFB bulk loader)."""
    if not face_targets:
        return 0
    ns.TargetService.bulk_load_targets(basemesh, [dict(t) for t in face_targets])
    _LOG.info(f"applied {len(face_targets)} face detail targets")
    for target in face_targets:
        _LOG.debug(f"  face target {target['target']} = {target['value']}")
    return len(face_targets)


def set_macro(ns, basemesh, name: str, value: float) -> None:
    ns.HumanObjectProperties.set_value(name, float(value), entity_reference=basemesh)
    ns.TargetService.reapply_macro_details(basemesh)
