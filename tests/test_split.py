from crucible.types import EvalItem
from crucible.datasets.split import stratified_split, weighted_sample


def _items(n, difficulty):
    return [EvalItem(f"q{i}", f"SELECT {i}", "world_1", difficulty) for i in range(n)]


def test_split_is_deterministic_and_disjoint():
    items = _items(10, "easy")
    tr1, te1 = stratified_split(items, test_frac=0.4, seed=7)
    tr2, te2 = stratified_split(items, test_frac=0.4, seed=7)
    assert [i.question for i in te1] == [i.question for i in te2]            # deterministic
    assert set(i.question for i in tr1).isdisjoint(i.question for i in te1)  # no leakage
    assert len(tr1) + len(te1) == 10                                         # complete


def test_split_preserves_strata():
    items = _items(10, "easy") + _items(10, "hard")
    tr, te = stratified_split(items, test_frac=0.5, seed=1)
    assert sum(i.difficulty == "hard" for i in te) == 5


def test_weighted_sample_respects_mix():
    pool = _items(100, "easy") + _items(100, "medium") + _items(100, "hard") + _items(100, "extra")
    out = weighted_sample(pool, n=20, seed=3)
    counts = {d: sum(i.difficulty == d for i in out) for d in ("easy", "medium", "hard", "extra")}
    assert counts["medium"] >= counts["easy"]   # medium weighted higher than easy
    assert counts["extra"] >= 1
