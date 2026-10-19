"""Tiny quad-mesh builder with per-loop UVs and per-vertex MakeClothes groups."""

import bpy


class MeshBuilder:
    def __init__(self):
        self.verts, self.groups, self.faces, self.face_uvs = [], [], [], []

    def add_vertex(self, co, group: str) -> int:
        self.verts.append(tuple(co))
        self.groups.append(group)
        return len(self.verts) - 1

    def add_quad(self, indices, uvs) -> None:
        """indices: 4 vertex ids (counter-clockwise seen from outside); uvs: 4 (u, v) tuples."""
        self.faces.append(tuple(indices))
        self.face_uvs.append(tuple(uvs))

    def to_object(self, name: str):
        used = sorted({i for face in self.faces for i in face})
        remap = {old: new for new, old in enumerate(used)}
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([self.verts[i] for i in used], [], [tuple(remap[i] for i in f) for f in self.faces])
        mesh.update()
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for poly, uvs in zip(mesh.polygons, self.face_uvs):
            for loop_index, uv in zip(poly.loop_indices, uvs):
                uv_layer.data[loop_index].uv = uv
        for poly in mesh.polygons:
            poly.use_smooth = True
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        for group_name in sorted(set(self.groups[i] for i in used)):
            group = obj.vertex_groups.new(name=group_name)
            group.add([remap[i] for i in used if self.groups[i] == group_name], 1.0, "REPLACE")
        return obj
