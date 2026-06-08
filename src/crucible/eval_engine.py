"""Score a candidate over a split: run each item, execute SQL, compare to gold."""
from crucible.types import CandidateSpec, EvalItem, EvalResult, ItemResult, ModelFn
from crucible.candidate import run_candidate_on_item
from crucible.comparator import compare_results, gold_requires_order
from crucible.sandbox import SqlSandbox


def evaluate(spec: CandidateSpec, schema_ddl: str, items: list[EvalItem],
             sandbox: SqlSandbox, model: ModelFn, split: str) -> EvalResult:
    results = []
    for item in items:
        predicted = run_candidate_on_item(spec, schema_ddl, item, model)
        pred_rows, pred_err = sandbox.run(predicted)
        if pred_err is not None:
            results.append(ItemResult(item, predicted, False, error=pred_err))
            continue
        gold_rows, _ = sandbox.run(item.gold_sql)
        match = compare_results(gold_rows, pred_rows, gold_requires_order(item.gold_sql))
        results.append(ItemResult(item, predicted, match.is_match))
    score = sum(r.is_match for r in results) / len(results) if results else 0.0
    return EvalResult(spec.version, split, score, tuple(results))
