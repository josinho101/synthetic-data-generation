"""Classify basemesh vertices into body regions using the default rig's weights."""

TORSO_BONES = {"root", "spine01", "spine02", "spine03", "spine04", "spine05",
               "breast.L", "breast.R", "pelvis.L", "pelvis.R",
               "clavicle.L", "clavicle.R", "shoulder01.L", "shoulder01.R"}
UPPER_ARM_BONES = {"upperarm01.L", "upperarm02.L", "upperarm01.R", "upperarm02.R"}


def dominant_bones(obj, bone_names) -> dict:
    """vertex index -> name of the rig bone whose weight group dominates that vertex."""
    names = {g.index: g.name for g in obj.vertex_groups if g.name in bone_names}
    result = {}
    for v in obj.data.vertices:
        best, best_w = None, 0.0
        for g in v.groups:
            if g.group in names and g.weight > best_w:
                best, best_w = names[g.group], g.weight
        result[v.index] = best
    return result


def arm_fraction(co, shoulder, elbow) -> float:
    """Position along the upper arm: 0 at the shoulder joint, 1 at the elbow joint."""
    axis = elbow - shoulder
    return (co - shoulder).dot(axis) / axis.length_squared
