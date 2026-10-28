"""Human rigs: which retarget map a human uses, and checks of its tag chains (no pxr needed).

Every human carries its rig id in <id>.json -> skeleton.rig (mpfb_default, zanatomy_anatomical, ...). isaac.yaml ->
retarget_maps names the retarget config for each rig id; `default` serves rigs not listed (and humans built before
the rig id was recorded).
"""

from .config import ConfigError

# Tagged segments whose direction is matched to the reference rig's T-pose (parent before child).
# Spine and neck stay as authored: the humans' spines are upright like the reference, and re-aiming them tilts the
# head back.
TPOSE_SEGMENTS = [
    seg for s in ("Left", "Right") for seg in (
        (f"{s}Shoulder", f"{s}Arm"), (f"{s}Arm", f"{s}ForeArm"), (f"{s}ForeArm", f"{s}Hand"),
        (f"{s}Hand", f"{s}HandMiddle2"), (f"{s}Leg", f"{s}Shin"), (f"{s}Shin", f"{s}Foot"), (f"{s}Foot", f"{s}ToeBase"))]

# Tag chains that must run down the skeleton: each tag's joint must be an ancestor of the next one's. Otherwise the
# motion of a tagged joint does not reach the next (e.g. a forearm bone that is a sibling of the hand's parent).
TAG_CHAINS = [["Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head"]] + [
    chain for s in ("Left", "Right") for chain in (
        ["Chest", f"{s}Shoulder", f"{s}Arm", f"{s}ForeArm", f"{s}Hand", f"{s}HandMiddle2"],
        ["Hips", f"{s}Leg", f"{s}Shin", f"{s}Foot", f"{s}ToeBase"])]


def rig_id(human_meta: dict) -> str:
    return str((human_meta.get("skeleton") or {}).get("rig") or "default")


def retarget_config_name(cfg: dict, rig: str) -> str:
    maps = cfg["isaac"].get("retarget_maps") or {"default": "retarget_mpfb"}
    name = maps.get(rig) or maps.get("default")
    if not name:
        raise ConfigError(f"no retarget map for rig {rig!r} in isaac.retarget_maps (and no default)")
    return name


def retarget_for(cfg: dict, rig: str) -> dict:
    """{config, tags, root_joint_name, up_axis, forward_axis} of the retarget map for this rig."""
    name = retarget_config_name(cfg, rig)
    block = cfg[name]
    return {"config": name, "tags": dict(block["tags"]),
            "root_joint_name": block.get("root_joint_name", "SkelOrigin"),
            "up_axis": block.get("up_axis", "Z"), "forward_axis": block.get("forward_axis", "MINUS Y")}


def check_tag_chains(joints, tags: dict) -> list:
    """Errors for tagged joints that are missing or not ancestors of the next tag in TAG_CHAINS.

    `joints` are the skeleton's joint paths ("SkelOrigin/pelvis/femur_L"), `tags` {tag: joint leaf name}."""
    path_of = {str(j).split("/")[-1]: str(j) for j in joints}
    errors = [f"{tag}: joint {leaf!r} is not in the skeleton" for tag, leaf in tags.items() if leaf not in path_of]
    for chain in TAG_CHAINS:
        present = [t for t in chain if t in tags and tags[t] in path_of]
        for upper, lower in zip(present, present[1:]):
            if not path_of[tags[lower]].startswith(path_of[tags[upper]] + "/"):
                errors.append(f"{lower} ({tags[lower]}) is not below {upper} ({tags[upper]}): "
                              f"{path_of[tags[lower]]}")
    return errors
