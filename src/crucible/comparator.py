"""Execution-match comparison: do two SQL result sets denote the same answer?

Pure, deterministic, and the highest-value unit in the system — every score depends on it.
Semantics: order-insensitive unless the gold query has ORDER BY; multiset rows (duplicates
count); strict column count; numeric tolerance; strings trimmed; NULL-aware.
"""
from collections import Counter

from crucible.types import MatchResult

NUMERIC_PRECISION = 6


def _normalize_cell(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), NUMERIC_PRECISION)
    if isinstance(value, str):
        return value.strip()
    return value


def _normalize_row(row):
    return tuple(_normalize_cell(c) for c in row)


def gold_requires_order(sql: str) -> bool:
    """True only for a TOP-LEVEL ORDER BY. An ORDER BY inside a subquery (paren depth
    > 0) does not constrain the outer result order, so it must not force ordered match."""
    s = sql.lower()
    depth = 0
    for i, c in enumerate(s):
        if c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and s.startswith("order by", i):
            return True
    return False


def compare_results(gold_rows, pred_rows, order_matters: bool) -> MatchResult:
    if gold_rows is None or pred_rows is None:
        return MatchResult(False, "null result set")
    g = [_normalize_row(r) for r in gold_rows]
    p = [_normalize_row(r) for r in pred_rows]
    gw = len(g[0]) if g else None
    pw = len(p[0]) if p else None
    if gw is not None and pw is not None and gw != pw:
        return MatchResult(False, f"column count differs: {gw} vs {pw}")
    if order_matters:
        ok = g == p
    else:
        ok = Counter(g) == Counter(p)
    return MatchResult(ok, "match" if ok else "rows differ")
