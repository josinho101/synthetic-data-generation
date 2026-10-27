"""Exact quota allocation.

Two ideas:
1. largest_remainder(): percentages -> integer counts that sum exactly to N.
2. assign_strata(): every factor's marginal is exact, and each factor is *interleaved*
   inside the groups formed by the earlier factors (e.g. ethnicity is balanced within
   each sex), because people are sorted by their earlier labels before the next
   factor's labels are dealt out in a proportional, evenly spread sequence.
"""

import random


def largest_remainder(percentages: dict, n: int) -> dict:
    """{'male': 50, 'female': 50}, 150 -> {'male': 75, 'female': 75} (exact sum)."""
    total = float(sum(percentages.values()))
    if total <= 0:
        raise ValueError("percentages must sum to a positive value")
    raw = {k: n * v / total for k, v in percentages.items()}
    counts = {k: int(v) for k, v in raw.items()}
    leftover = n - sum(counts.values())
    # ties are broken by declaration order so the result is deterministic
    order = sorted(raw, key=lambda k: (-(raw[k] - counts[k]), list(raw).index(k)))
    for key in order[:leftover]:
        counts[key] += 1
    return counts


def proportional_sequence(counts: dict) -> list:
    """Spread labels evenly: {'a': 2, 'b': 4} -> ['b', 'a', 'b', 'b', 'a', 'b'].

    At each position the label furthest behind its ideal share is emitted, so every
    prefix of the sequence is close to proportional (sequential apportionment).
    """
    n = sum(counts.values())
    emitted = {k: 0 for k in counts}
    sequence = []
    for i in range(1, n + 1):
        best = max(
            (k for k in counts if emitted[k] < counts[k]),
            key=lambda k: (counts[k] * i / n - emitted[k], counts[k]),
        )
        emitted[best] += 1
        sequence.append(best)
    return sequence


def assign_strata(n: int, factors: list, rng: random.Random) -> list:
    """factors: [(name, {label: pct}), ...] in stratify order. Returns n dicts of labels."""
    people = [dict() for _ in range(n)]
    for name, percentages in factors:
        counts = largest_remainder(percentages, n)
        sequence = proportional_sequence(counts)
        # group by earlier labels; shuffle inside groups so ties are random but seeded
        indices = list(range(n))
        rng.shuffle(indices)
        prior = [f for f, _ in factors[: [f for f, _ in factors].index(name)]]
        indices.sort(key=lambda i: tuple(people[i][f] for f in prior))
        for label, idx in zip(sequence, indices):
            people[idx][name] = label
    rng.shuffle(people)
    return people
