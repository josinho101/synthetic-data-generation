"""Build context shared by the USD builders: stage, materials, flags and mesh shortcuts."""

from pxr import UsdGeom, UsdPhysics

from .stage import Looks, add_collider, add_semantics, bind, box_mesh, cylinder_mesh, safe_name, xform


class BuildContext:
    def __init__(self, stage, root_path, cfg, spec, texture_dir, texture_rel="textures"):
        self.stage, self.root, self.cfg, self.spec = stage, root_path, cfg, spec
        self.looks = Looks(stage, root_path)
        self.texture_dir = texture_dir      # absolute directory of the PNGs
        self.texture_rel = texture_rel      # path written into the USD (relative to the USD file)
        export = cfg["export"]
        self.colliders = export["physics"]["colliders"]
        self.approximation = export["physics"]["approximation"]
        self.props_rigid = export["physics"].get("props_rigid_body", False)
        self.semantics = export.get("semantics", True)
        self.segments = export["usd"].get("cylinder_segments", 24)
        self.labels = {}                    # prim path -> semantic label (reported in metadata)

    def tex(self, filename: str) -> str:
        return f"./{self.texture_rel}/{filename}"

    def group(self, path, translate=(0, 0, 0), rotate=(0, 0, 0), label=None):
        xf = xform(self.stage, path, translate, rotate)
        if label:
            self.label(xf.GetPrim(), label)
        return xf

    def label(self, prim, label):
        if self.semantics:
            add_semantics(prim, label)
        self.labels[str(prim.GetPath())] = label

    def box(self, parent, name, size, center, material, uv=1.0, collide=True):
        mesh = box_mesh(self.stage, f"{parent}/{safe_name(name)}", size, center, uv)
        bind(mesh.GetPrim(), material)
        if collide and self.colliders:
            add_collider(mesh.GetPrim(), self.approximation)
        return mesh

    def cyl(self, parent, name, radius, length, axis, center, material, collide=True):
        mesh = cylinder_mesh(self.stage, f"{parent}/{safe_name(name)}", radius, length, axis, center, self.segments)
        bind(mesh.GetPrim(), material)
        if collide and self.colliders:
            add_collider(mesh.GetPrim(), self.approximation)
        return mesh

    def rigid(self, prim, mass_kg=None):
        """Optional dynamic rigid body for a prop group (export.physics.props_rigid_body)."""
        if not (self.props_rigid and self.colliders):
            return
        UsdPhysics.RigidBodyAPI.Apply(prim)
        if mass_kg:
            UsdPhysics.MassAPI.Apply(prim).CreateMassAttr().Set(float(mass_kg))

    def reference_asset(self, path, asset_path) -> bool:
        """Replace a procedural part by an external USD asset (equipment.yaml `asset:`)."""
        if not asset_path:
            return False
        prim = self.stage.GetPrimAtPath(path) or UsdGeom.Xform.Define(self.stage, path).GetPrim()
        prim.GetReferences().AddReference(str(asset_path))
        return True
