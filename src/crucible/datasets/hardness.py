"""Spider-style difficulty classifier.

Approximates Spider's official hardness (github.com/taoyds/spider) by counting SQL
components. Used only for difficulty-weighted sampling, never for scoring.
"""
import re

_AGG = ("count(", "sum(", "avg(", "max(", "min(")


def _components(sql: str) -> int:
    s = sql.lower()
    score = 0
    score += len(re.findall(r"\bjoin\b", s))
    score += 1 if " where " in s else 0
    score += 1 if " group by" in s else 0
    score += 1 if " having" in s else 0
    score += 1 if " order by" in s else 0
    score += sum(s.count(a) for a in _AGG)
    score += s.count(" union ") + s.count(" intersect ") + s.count(" except ")
    score += s.count(" or ")
    return score


def classify_hardness(sql: str) -> str:
    s = sql.lower()
    from_idx = s.find(" from ")
    nested = from_idx != -1 and "select" in s[from_idx + 6:]
    comp = _components(sql)
    if nested or comp >= 5:
        return "extra"
    if comp >= 3:
        return "hard"
    if comp >= 1:
        return "medium"
    return "easy"
