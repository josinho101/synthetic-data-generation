"""Generated eyes for builds without an eye asset pack.

The basemesh carries eye helper geometry (helper-l-eye / helper-r-eye) inside the
sockets. It is copied into its own mesh, split into sclera / iris / pupil material
slots by the angle to the eye's forward axis (-Y), and bound to the eye bones.
"""

import logging
import math

import bmesh
import bpy
from mathutils import Vector

from . import bake, colors, geometry

_LOG = logging.getLogger("sdg_humans.blender.eyes")

_IRIS_COS = math.cos(math.radians(32))
_PUPIL_COS = math.cos(math.radians(13))


def _eye_object(basemesh, coords, group_name: str, name: str):
    indices = set(geometry.group_vertex_indices(basemesh, group_name))
    bm = bmesh.new()
    bm.from_mesh(basemesh.data)
    geometry.strip_layers(bm)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        v.co = coords[v.index]
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in indices], context="VERTS")
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _assign_slots(obj, materials) -> None:
    for material in materials:
        obj.data.materials.append(material)
    centre = sum((v.co for v in obj.data.vertices), Vector()) / max(1, len(obj.data.vertices))
    forward = Vector((0.0, -1.0, 0.0))
    for poly in obj.data.polygons:
        direction = (poly.center - centre).normalized()
        cos = direction.dot(forward)
        poly.material_index = 2 if cos > _PUPIL_COS else (1 if cos > _IRIS_COS else 0)
        poly.use_smooth = True


def _bind(obj, armature, bone_name: str) -> None:
    group = obj.vertex_groups.new(name=bone_name)
    group.add([v.index for v in obj.data.vertices], 1.0, "REPLACE")
    obj.parent = armature
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature


def build_eyes(basemesh, armature, spec: dict, appearance: dict) -> list:
    coords = geometry.evaluated_coords(basemesh)
    iris_hex = appearance["eyes"]["rgb"].get(spec["eyes"]["color"], "#5b3a1e")
    materials = [
        bake.simple_material(f"{spec['id']}_sclera", color=colors.hex_to_linear_rgba("#ece8e1"), roughness=0.15),
        bake.simple_material(f"{spec['id']}_iris", color=colors.hex_to_linear_rgba(iris_hex), roughness=0.2),
        bake.simple_material(f"{spec['id']}_pupil", color=(0.005, 0.005, 0.005, 1.0), roughness=0.1),
    ]
    created = []
    for side, group in (("L", "helper-l-eye"), ("R", "helper-r-eye")):
        obj = _eye_object(basemesh, coords, group, f"{spec['id']}_eye_{side}")
        _assign_slots(obj, materials)
        bone = f"eye.{side}" if f"eye.{side}" in armature.data.bones else "head"
        _bind(obj, armature, bone)
        created.append(obj)
    _LOG.info(f"generated eyes ({spec['eyes']['color']}) bound to eye bones")
    return created
