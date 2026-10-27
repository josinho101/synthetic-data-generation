"""Appendicular skeleton: clavicles, scapulae, hip bones, long bones, patellae, hands, feet."""

from ..geometry import Vector

from .prims import MeshAcc, bilinear, blend, ellipsoid, patch, tube

POSTERIOR = Vector((0.0, 1.0, 0.0))
ANTERIOR = Vector((0.0, -1.0, 0.0))


def _rigid(bone):
    return lambda t: {bone: 1.0}


def shoulder_girdle(ctx) -> dict:
    lm, s, head = ctx["lm"], ctx["s"], ctx["head"]
    out = {}
    for side, sign in (("L", 1), ("R", -1)):
        acromion = lm[f"acromion_{side}"] + Vector((-sign * 0.012 * s, 0.005 * s, -0.012 * s))
        sternal = lm["jugular_notch"] + Vector((sign * 0.018 * s, 0.012 * s, -0.004 * s))
        mid = sternal.lerp(acromion, 0.45) + ANTERIOR * 0.01 * s
        clavicle = MeshAcc()
        tube(clavicle, [sternal, mid, acromion], 0.0055 * s, _rigid(f"clavicle.{side}"), segments=8)
        out[f"clavicle_{side}"] = (clavicle, f"clavicle.{side}", None)

        t2, t7 = lm["T2"], lm["T7"]
        def on_back(x, z):
            p = ctx["back_point"](x, z)
            return p if p is not None else Vector((x, t2.y + 0.05 * s, z))
        superior = on_back(sign * 0.055 * s, t2.z)
        inferior = on_back(sign * 0.085 * s, t7.z)
        glenoid = head(f"upperarm01.{side}") + Vector((-sign * 0.015 * s, 0.02 * s, 0.0))
        spine_end = acromion + POSTERIOR * 0.015 * s
        grid = bilinear(superior, spine_end, glenoid, inferior, 5, 5)
        grid = [[ctx["back_point"](p.x, p.z) or p for p in row] for row in grid]
        scapula = MeshAcc()
        patch(scapula, grid, f"shoulder01.{side}")
        out[f"scapula_{side}"] = (scapula, f"shoulder01.{side}", 0.006 * s)
    return out


def pelvis(ctx) -> dict:
    lm, s, head = ctx["lm"], ctx["s"], ctx["head"]
    out = {}
    for side, sign in (("L", 1), ("R", -1)):
        bone = f"pelvis.{side}"
        acetabulum = head(f"upperleg01.{side}") + Vector((sign * 0.01 * s, 0.0, 0.01 * s))
        crest = lm[f"iliac_crest_{side}"] + Vector((-sign * 0.012 * s, 0.0, -0.008 * s))
        asis = lm[f"asis_{side}"] + POSTERIOR * 0.015 * s
        psis = lm["S1"] + Vector((sign * 0.045 * s, 0.01 * s, 0.005 * s))
        ilium = MeshAcc()
        patch(ilium, bilinear(psis, crest, asis, acetabulum, 5, 5), bone)
        out[f"ilium_{side}"] = (ilium, bone, 0.007 * s)
        symphysis = Vector((sign * 0.012 * s, asis.y + 0.03 * s, acetabulum.z - 0.035 * s))
        ischium = acetabulum + Vector((-sign * 0.01 * s, 0.035 * s, -0.075 * s))
        ring = MeshAcc()
        tube(ring, [acetabulum, symphysis.lerp(acetabulum, 0.4), symphysis,
                    symphysis + Vector((0.0, 0.01 * s, -0.035 * s)), ischium, acetabulum],
             0.0065 * s, _rigid(bone), segments=8, caps=False)
        out[f"ischiopubic_{side}"] = (ring, bone, None)
    return out


def _long_bone(acc, start, end, radius, weights_fn, knob_start, knob_end):
    tube(acc, [start.lerp(end, f) for f in (0.0, 0.15, 0.5, 0.85, 1.0)],
         [radius * 1.5, radius, radius * 0.9, radius, radius * 1.5], weights_fn, segments=10)
    ellipsoid(acc, start, (knob_start,) * 3, weights_fn(0.0))
    ellipsoid(acc, end, (knob_end, knob_end, knob_end * 0.8), weights_fn(1.0))


def limbs(ctx) -> dict:
    s, head, tail, lateral, lm = ctx["s"], ctx["head"], ctx["tail"], ctx["lateral"], ctx["lm"]
    out = {}
    for side, sign in (("L", 1), ("R", -1)):
        arm = MeshAcc()
        _long_bone(arm, head(f"upperarm01.{side}"), tail(f"upperarm02.{side}"), 0.010 * s,
                   blend(f"upperarm01.{side}", f"upperarm02.{side}"), 0.022 * s, 0.017 * s)
        out[f"humerus_{side}"] = (arm, f"upperarm01.{side}", None)
        elbow, wrist = head(f"lowerarm01.{side}"), tail(f"lowerarm02.{side}")
        offset = lateral(f"lowerarm01.{side}") * 0.009 * s
        for name, shift, r in (("radius", offset, 0.006 * s), ("ulna", -offset, 0.0065 * s)):
            acc = MeshAcc()
            tube(acc, [(elbow + shift).lerp(wrist + shift, f) for f in (0.0, 0.5, 1.0)], r,
                 blend(f"lowerarm01.{side}", f"lowerarm02.{side}"), segments=8)
            out[f"{name}_{side}"] = (acc, f"lowerarm01.{side}", None)

        thigh = MeshAcc()
        hip, knee = head(f"upperleg01.{side}"), tail(f"upperleg02.{side}")
        shaft_top = hip.lerp(knee, 0.08) + Vector((sign * 0.035 * s, 0.0, 0.0))
        _long_bone(thigh, shaft_top, knee, 0.013 * s, blend(f"upperleg01.{side}", f"upperleg02.{side}"),
                   0.016 * s, 0.026 * s)
        tube(thigh, [hip, shaft_top], 0.011 * s, _rigid(f"upperleg01.{side}"), segments=8)
        ellipsoid(thigh, hip, (0.023 * s,) * 3, f"upperleg01.{side}")
        trochanter = lm[f"greater_trochanter_{side}"] + Vector((-sign * 0.02 * s, 0.0, 0.0))
        ellipsoid(thigh, trochanter, (0.012 * s, 0.015 * s, 0.02 * s), f"upperleg01.{side}")
        out[f"femur_{side}"] = (thigh, f"upperleg01.{side}", None)

        knee_joint, ankle = head(f"lowerleg01.{side}"), tail(f"lowerleg02.{side}")
        patella = MeshAcc()
        ellipsoid(patella, knee_joint + ANTERIOR * 0.035 * s + Vector((0, 0, 0.012 * s)),
                  (0.02 * s, 0.009 * s, 0.024 * s), f"lowerleg01.{side}")
        out[f"patella_{side}"] = (patella, f"lowerleg01.{side}", None)
        tibia = MeshAcc()
        _long_bone(tibia, knee_joint - Vector((0, 0, 0.015 * s)), ankle, 0.012 * s,
                   blend(f"lowerleg01.{side}", f"lowerleg02.{side}"), 0.028 * s, 0.016 * s)
        out[f"tibia_{side}"] = (tibia, f"lowerleg01.{side}", None)
        fibula = MeshAcc()
        fib_shift = Vector((sign * 0.022 * s, 0.012 * s, 0.0))
        tube(fibula, [knee_joint + fib_shift - Vector((0, 0, 0.03 * s)), ankle + fib_shift * 0.8], 0.0055 * s,
             blend(f"lowerleg01.{side}", f"lowerleg02.{side}"), segments=8)
        out[f"fibula_{side}"] = (fibula, f"lowerleg01.{side}", None)
    return out


def hands_feet(ctx) -> dict:
    s, head, tail, bones, lm = ctx["s"], ctx["head"], ctx["tail"], ctx["bones"], ctx["lm"]
    out = {}
    for side in ("L", "R"):
        hand = MeshAcc()
        wrist = f"wrist.{side}"
        ellipsoid(hand, head(wrist).lerp(tail(wrist), 0.5), (0.02 * s, 0.012 * s, 0.015 * s), wrist)
        for name in bones:
            if name.endswith(f".{side}") and name.startswith(("finger", "metacarpal")):
                tube(hand, [head(name), tail(name)], 0.0042 * s, _rigid(name), segments=6)
        out[f"hand_{side}"] = (hand, wrist, None)

        foot = MeshAcc()
        fb = f"foot.{side}"
        ankle, ball = head(fb), tail(fb)
        ellipsoid(foot, ankle.lerp(ball, 0.3) + Vector((0, 0, -0.01 * s)), (0.022 * s, 0.035 * s, 0.018 * s), fb)
        tube(foot, [ankle - Vector((0, 0, 0.02 * s)), lm[f"heel_{side}"] + Vector((0, -0.012 * s, 0.015 * s))],
             0.013 * s, _rigid(fb), segments=8)
        for name in bones:
            if name.endswith(f".{side}") and name.startswith("toe"):
                tube(foot, [head(name), tail(name)], 0.0045 * s, _rigid(name), segments=6)
                if name.split("-")[1].startswith("1"):  # metatarsal to the first phalanx
                    tube(foot, [ankle.lerp(ball, 0.45), head(name)], 0.005 * s, _rigid(fb), segments=6)
        out[f"foot_{side}"] = (foot, fb, None)
    return out
