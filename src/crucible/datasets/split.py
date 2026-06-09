"""Stratified train/test split + difficulty-weighted sampling.

The split keeps the test set held-out so the reported climb proves generalization, not
memorization of the examples the agent mutated against.
"""
import random
from collections import defaultdict

from crucible.types import EvalItem

DEFAULT_WEIGHTS = {"easy": 0.20, "medium": 0.35, "hard": 0.30, "extra": 0.15}


def stratified_split(items: list[EvalItem], test_frac: float = 0.4, seed: int = 0):
    by_diff = defaultdict(list)
    for it in items:
        by_diff[it.difficulty].append(it)
    rng = random.Random(seed)
    train, test = [], []
    for group in by_diff.values():
        g = group[:]
        rng.shuffle(g)
        k = round(len(g) * test_frac)
        test.extend(g[:k])
        train.extend(g[k:])
    return train, test


def weighted_sample(items: list[EvalItem], n: int, weights=None, seed: int = 0):
    weights = weights or DEFAULT_WEIGHTS
    by_diff = defaultdict(list)
    for it in items:
        by_diff[it.difficulty].append(it)
    rng = random.Random(seed)
    out = []
    used = set()
    for diff, w in weights.items():
        group = by_diff.get(diff, [])[:]
        rng.shuffle(group)
        take = min(len(group), round(n * w))
        for it in group[:take]:
            out.append(it)
            used.add(id(it))
    # Per-stratum rounding can sum to fewer than n; top up from leftovers to hit n.
    if len(out) < n:
        remaining = [it for it in items if id(it) not in used]
        rng.shuffle(remaining)
        out.extend(remaining[: n - len(out)])
    rng.shuffle(out)
    return out
