"""Score a candidate over a split: run each item, execute SQL, compare to gold."""
from typing import Callable, Optional

from crucible.types import CandidateSpec, EvalItem, EvalResult, ItemResult, ModelFn
from crucible.candidate import run_candidate_on_item
from crucible.comparator import compare_results, gold_requires_order
from crucible.sandbox import SqlSandbox

# (split, item, predicted_sql, is_match, error) -> None. Optional per-item hook so
# callers (e.g. the SSE server) can stream each scored question as it happens.
OnItemFn = Callable[[str, EvalItem, str, bool, Optional[str]], None]


def evaluate(spec: CandidateSpec, schema_ddl: str, items: list[EvalItem],
             sandbox: SqlSandbox, model: ModelFn, split: str,
             on_item: Optional[OnItemFn] = None) -> EvalResult:
    results = []
    scored = 0          # items we could actually grade (gold executed)
    matched = 0

    def report(item: EvalItem, predicted: str, is_match: bool, error: Optional[str]) -> None:
        if on_item is not None:
            on_item(split, item, predicted, is_match, error)

    for item in items:
        predicted = run_candidate_on_item(spec, schema_ddl, item, model)
        pred_rows, pred_err = sandbox.run(predicted)
        if pred_err is not None:                         # agent produced invalid SQL -> a real failure
            results.append(ItemResult(item, predicted, False, error=pred_err))
            scored += 1
            report(item, predicted, False, pred_err)
            continue
        gold_rows, gold_err = sandbox.run(item.gold_sql)
        if gold_err is not None:                         # broken gold: a dataset bug, not the agent's fault
            results.append(ItemResult(item, predicted, False, error=f"[gold] {gold_err}"))
            report(item, predicted, False, f"[gold] {gold_err}")
            continue                                     # excluded from the score so it can't skew the climb
        match = compare_results(gold_rows, pred_rows, gold_requires_order(item.gold_sql))
        results.append(ItemResult(item, predicted, match.is_match))
        scored += 1
        matched += int(match.is_match)
        report(item, predicted, match.is_match, None)
    score = matched / scored if scored else 0.0
    return EvalResult(spec.version, split, score, tuple(results))
