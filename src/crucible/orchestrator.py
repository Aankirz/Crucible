"""The reflexive optimization loop.

Each round: score the candidate, let the agent read its own failures (via MCP), pick the
dominant failure cluster, propose ONE atomic mutation, and accept it only if it improves
the TRAIN score. The held-out TEST score is the headline number; the best-so-far version is
always retained and promoted. Stops on target / max-iters / patience.
"""
from dataclasses import dataclass
from typing import Callable

from crucible.types import CandidateSpec, EvalResult, ModelFn
from crucible.eval_engine import evaluate
from crucible.mutation import classify_failure, pick_top_cluster, propose_mutation, apply_hypothesis


@dataclass(frozen=True)
class LoopConfig:
    max_iters: int = 6
    target: float = 0.9
    patience: int = 2


def _classify_all(result: EvalResult) -> EvalResult:
    items = tuple(
        r if r.is_match
        else r.__class__(r.item, r.predicted_sql, r.is_match, r.error, classify_failure(r))
        for r in result.item_results
    )
    return EvalResult(result.spec_version, result.split, result.score, items)


def run_loop(initial_spec: CandidateSpec, schema_ddl: str, train, test,
             sandbox, candidate_model: ModelFn, mutation_model: ModelFn,
             introspect: Callable[[str], str], log_experiment: Callable,
             on_event: Callable, db_id: str, config: LoopConfig = LoopConfig()):
    history = []
    spec = initial_spec
    train_res = _classify_all(evaluate(spec, schema_ddl, train, sandbox, candidate_model, "train"))
    test_res = evaluate(spec, schema_ddl, test, sandbox, candidate_model, "test")
    log_experiment(test_res, db_id)
    # Log the train split too and keep the name it was stored under: introspection
    # reads THIS experiment's failing rows via MCP. Using the returned name avoids
    # guessing the storage format (the cause of the prior name-mismatch bug).
    train_name = log_experiment(train_res, db_id)
    best = (spec, test_res)
    history.append((spec.version, train_res.score, test_res.score))
    on_event({"type": "version", "version": spec.version,
              "train": train_res.score, "test": test_res.score})

    no_improve = 0
    for _ in range(config.max_iters):
        if test_res.score >= config.target:
            break
        mcp_summary = introspect(train_name)                   # agent-initiated MCP read of own failures
        failures = [r for r in train_res.item_results
                    if not r.is_match and not (r.error or "").startswith("[gold]")]
        category = pick_top_cluster(failures)
        if category is None:
            break
        on_event({"type": "hypothesis", "category": category, "mcp_summary": mcp_summary})
        hyp = propose_mutation(spec, category, failures, mutation_model, mcp_summary)
        if not hyp.instruction_add and not hyp.few_shots:      # empty/garbled proposal: don't waste a version
            no_improve += 1
            on_event({"type": "rejected", "version": spec.version + 1})
            if no_improve >= config.patience:
                break
            continue
        candidate = apply_hypothesis(spec, hyp)
        cand_train = _classify_all(
            evaluate(candidate, schema_ddl, train, sandbox, candidate_model, "train"))
        if cand_train.score > train_res.score:                  # accept on TRAIN improvement
            spec, train_res = candidate, cand_train
            test_res = evaluate(spec, schema_ddl, test, sandbox, candidate_model, "test")
            log_experiment(test_res, db_id)
            train_name = log_experiment(train_res, db_id)       # refresh: introspection reads the new train failures
            if test_res.score > best[1].score:
                best = (spec, test_res)
            no_improve = 0
            history.append((spec.version, train_res.score, test_res.score))
            on_event({"type": "version", "version": spec.version,
                      "train": train_res.score, "test": test_res.score})
        else:                                                  # reject + revert (spec unchanged)
            no_improve += 1
            on_event({"type": "rejected", "version": candidate.version})
            if no_improve >= config.patience:
                break

    on_event({"type": "promoted", "version": best[0].version, "test": best[1].score})
    return best, history
