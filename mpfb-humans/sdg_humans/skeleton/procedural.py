"""The skeletal layers that keep the MPFB rig: 'procedural' (bones built in Blender) and 'none'."""

from . import SkeletonLayer


class ProceduralLayer(SkeletonLayer):
    """Bone meshes generated in Blender from the MPFB rig and landmarks (blender/anatomy/, configs/anatomy.yaml).
    Nothing to do on the host: the build already exported them as bone_* meshes skinned to the MPFB rig."""
    name = "procedural"
    version = "1"
    builds_in_blender = True


class NoSkeletonLayer(SkeletonLayer):
    """No bone meshes; the MPFB rig (with its LM_ / AN_ landmark joints) is the only skeleton."""
    name = "none"
    version = "1"
