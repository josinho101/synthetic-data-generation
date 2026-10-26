"""Add the MPFB default rig (163 bones) and bind the body to it."""

import logging

_LOG = logging.getLogger("sdg_humans.blender.rig")


def add_default_rig(ns, basemesh):
    armature = ns.HumanService.add_builtin_rig(basemesh, "default", import_weights=True)
    if armature is None:
        raise RuntimeError("MPFB failed to add the default rig")
    armature.name = f"{basemesh.name}_rig"
    _LOG.info(f"default rig added: {len(armature.data.bones)} bones")
    return armature


def lift_to_floor(armature) -> float:
    """Raise the dressed human so the lowest point of any mesh (shoe soles) touches z = 0.
    Returns the lift in metres (0 when barefoot)."""
    import bpy
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    lowest = None
    for obj in armature.children_recursive:
        if obj.type != "MESH" or obj.name.startswith("bone_"):
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        matrix = evaluated.matrix_world
        z = min(((matrix @ v.co).z for v in mesh.vertices), default=None)
        evaluated.to_mesh_clear()
        if z is not None:
            lowest = z if lowest is None else min(lowest, z)
    if lowest is None or lowest >= -0.001:
        return 0.0
    armature.location.z -= lowest
    bpy.context.view_layer.update()
    _LOG.info(f"lifted {-lowest * 100:.1f} cm so the footwear stands on the floor")
    return -lowest
