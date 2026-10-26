"""Read landmark joint positions from a generated human (pxr only - usable inside Isaac Sim).

    from sdg_humans.isaac_landmarks import LandmarkReader
    reader = LandmarkReader(stage, "/World/Patients/H0001/H0001_rig/H0001_rig")
    positions = reader.world_positions(time)      # {"T7": (x, y, z), "tragus_L": (...), ...}

The skeleton prim path inside the human's USD is in <id>.json -> skeleton.usd_skeleton_prim
(prefix it with the prim you referenced the human under).
"""

from pxr import Usd, UsdGeom, UsdSkel


class LandmarkReader:
    def __init__(self, stage, skeleton_prim_path: str, prefix: str = "LM_"):
        self.skel_prim = stage.GetPrimAtPath(skeleton_prim_path)
        if not self.skel_prim or not self.skel_prim.IsA(UsdSkel.Skeleton):
            raise ValueError(f"{skeleton_prim_path} is not a UsdSkel Skeleton")
        self.cache = UsdSkel.Cache()
        self.query = self.cache.GetSkelQuery(UsdSkel.Skeleton(self.skel_prim))
        self.prefix = prefix
        self.indices = {path.split("/")[-1][len(prefix):]: i for i, path in enumerate(self.query.GetJointOrder())
                        if path.split("/")[-1].startswith(prefix)}

    @property
    def names(self) -> list:
        return sorted(self.indices)

    def world_positions(self, time=Usd.TimeCode.Default()) -> dict:
        """{landmark: (x, y, z)} in stage units for the given time (follows the animated skeleton)."""
        skel_space = self.query.ComputeJointSkelTransforms(time)
        to_world = UsdGeom.Xformable(self.skel_prim).ComputeLocalToWorldTransform(time)
        return {name: tuple((skel_space[i] * to_world).ExtractTranslation()) for name, i in self.indices.items()}
