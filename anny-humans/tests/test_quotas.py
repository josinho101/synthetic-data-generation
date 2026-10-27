import random
from collections import Counter

from anny_humans.sampling.quotas import assign_strata, largest_remainder, proportional_sequence


def test_largest_remainder_exact_sum():
    assert largest_remainder({"male": 50, "female": 50}, 150) == {"male": 75, "female": 75}
    counts = largest_remainder({"a": 20, "b": 20, "c": 20, "d": 25, "e": 15}, 151)
    assert sum(counts.values()) == 151


def test_proportional_sequence_spreads_labels():
    seq = proportional_sequence({"a": 2, "b": 4})
    assert Counter(seq) == {"a": 2, "b": 4}
    assert seq[:3].count("a") == 1  # evenly spread, not clustered


def test_assign_strata_marginals_exact_and_balanced():
    factors = [("sex", {"male": 50, "female": 50}), ("eth", {"x": 20, "y": 20, "z": 60})]
    people = assign_strata(150, factors, random.Random(1))
    assert Counter(p["sex"] for p in people) == {"male": 75, "female": 75}
    assert Counter(p["eth"] for p in people) == {"x": 30, "y": 30, "z": 90}
    joint = Counter((p["sex"], p["eth"]) for p in people)
    assert abs(joint[("male", "x")] - joint[("female", "x")]) <= 1


def test_assign_strata_deterministic():
    factors = [("sex", {"male": 30, "female": 70})]
    assert assign_strata(20, factors, random.Random(5)) == assign_strata(20, factors, random.Random(5))
