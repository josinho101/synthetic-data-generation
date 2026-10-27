"""Identity distance between two humans, used to guarantee distinct individuals.

distance = sqrt((body_rms^2 + face_rms^2) / 2)
  body_rms : RMS difference of the normalised body features
             (gender, age, muscle, weight, proportions, race mix, height, skin tone). Age enters as years / 130,
             the adult slope of the MPFB age macro: Anny's calibrated age phenotype spans only 0.77-0.85
             for 18-70 years and would hardly separate ages.
  face_rms : RMS difference of face target values over the union of targets used by
             either human (a target missing on one side counts as 0)
"""

import math


def body_features(spec: dict) -> list:
    m = spec["macros"]
    return [m["gender"], spec["age_years"] / 130.0, m["muscle"], m["weight"], m["proportions"],
            m["race"]["asian"], m["race"]["caucasian"], m["race"]["african"],
            (spec["target_height_cm"] - 140.0) / 70.0,
            spec["skin"]["tone_mst"] / 10.0]


def _rms(pairs) -> float:
    pairs = list(pairs)
    if not pairs:
        return 0.0
    return math.sqrt(sum((a - b) ** 2 for a, b in pairs) / len(pairs))


def identity_distance(a: dict, b: dict) -> float:
    body = _rms(zip(body_features(a), body_features(b)))
    face_a = {t["target"]: t["value"] for t in a["face_targets"]}
    face_b = {t["target"]: t["value"] for t in b["face_targets"]}
    names = set(face_a) | set(face_b)
    face = _rms((face_a.get(n, 0.0), face_b.get(n, 0.0)) for n in names)
    return math.sqrt((body ** 2 + face ** 2) / 2.0)


def min_distance(candidate: dict, accepted: list) -> float:
    return min((identity_distance(candidate, other) for other in accepted), default=float("inf"))
