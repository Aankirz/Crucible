"""The reflexive optimization loop.

Each round: score the candidate, let the agent read its own failures (via MCP), pick the
dominant failure cluster, propose ONE atomic mutation, and accept it only if it improves
the TRAIN score. The held-out TEST score is the headline number; the best-so-far version is
always retained and promoted. Stops on target / max-iters / patience.
"""
import os
from dataclasses import dataclass
from typing import Callable, Optional

from crucible.types import CandidateSpec, EvalItem, EvalResult, ModelFn
from crucible.eval_engine import evaluate
from crucible.mutation import classify_failure, pick_top_cluster, propose_mutation, apply_hypothesis


@dataclass(frozen=True)
class LoopConfig:
    max_iters: int = 6
    target: float = 0.9
    patience: int = 2


def _phoenix_url(experiment: str) -> str:
    """Build a best-effort Phoenix deep link, or "" when unconfigured.

    There is no documented stable per-experiment URL scheme, so we link to the
    experiments view of the configured collector endpoint, tagging the experiment
    name as a query param. Returns "" when no endpoint is configured.
    """
    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    if not endpoint:
        return ""
    base = endpoint.rstrip("/")
    return f"{base}/experiments?name={experiment}"


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
             on_event: Callable, db_id: str, config: LoopConfig = LoopConfig(),
             on_item: Optional[Callable] = None):
    history = []
    spec = initial_spec

    def status(phase: str, message: str) -> None:
        """Emit a human-readable step event for the live activity log."""
        on_event({"type": "status", "phase": phase, "message": message})

    def item_reporter(version: int):
        """Build a per-item callback that tags each scored question with `version`.

        Returns None when no on_item sink is wired, so `evaluate` skips the work.
        """
        if on_item is None:
            return None

        def _report(split: str, ev_item: EvalItem, predicted_sql: str,
                    is_match: bool, error) -> None:
            on_item({
                "type": "item",
                "version": version,
                "split": split,
                "question": ev_item.question,
                "predicted_sql": predicted_sql,
                "is_match": is_match,
                "error": error,
            })

        return _report

    def log_and_announce(result: EvalResult) -> str:
        """Log an experiment and emit a best-effort `phoenix` event; return its name."""
        name = log_experiment(result, db_id)
        on_event({
            "type": "phoenix",
            "experiment": name,
            "url": _phoenix_url(name),
            "split": result.split,
            "version": result.spec_version,
        })
        return name

    status("start", f"Starting optimization for '{db_id}'.")
    status("scoring", f"Scoring baseline candidate v{spec.version}.")
    train_res = _classify_all(
        evaluate(spec, schema_ddl, train, sandbox, candidate_model, "train",
                 item_reporter(spec.version)))
    test_res = evaluate(spec, schema_ddl, test, sandbox, candidate_model, "test",
                        item_reporter(spec.version))
    on_event({"type": "version", "version": spec.version,
              "train": train_res.score, "test": test_res.score})
    log_and_announce(test_res)
    # Log the train split too and keep the name it was stored under: introspection
    # reads THIS experiment's failing rows via MCP. Using the returned name avoids
    # guessing the storage format (the cause of the prior name-mismatch bug).
    train_name = log_and_announce(train_res)
    best = (spec, test_res)
    history.append((spec.version, train_res.score, test_res.score))

    no_improve = 0
    for _ in range(config.max_iters):
        if test_res.score >= config.target:
            break
        status("introspecting", "Reading the agent's own failing traces.")
        mcp_summary = introspect(train_name)                   # agent-initiated MCP read of own failures
        failures = [r for r in train_res.item_results
                    if not r.is_match and not (r.error or "").startswith("[gold]")]
        category = pick_top_cluster(failures)
        if category is None:
            break
        on_event({"type": "hypothesis", "category": category, "mcp_summary": mcp_summary})
        status("mutating", f"Proposing one atomic fix for '{category}' failures.")
        hyp = propose_mutation(spec, category, failures, mutation_model, mcp_summary)
        if not hyp.instruction_add and not hyp.few_shots:      # empty/garbled proposal: don't waste a version
            no_improve += 1
            status("rejected", f"Empty proposal for v{spec.version + 1}; reverting.")
            on_event({"type": "rejected", "version": spec.version + 1})
            if no_improve >= config.patience:
                break
            continue
        candidate = apply_hypothesis(spec, hyp)
        status("scoring", f"Scoring candidate v{candidate.version}.")
        cand_train = _classify_all(
            evaluate(candidate, schema_ddl, train, sandbox, candidate_model, "train",
                     item_reporter(candidate.version)))
        if cand_train.score > train_res.score:                  # accept on TRAIN improvement
            spec, train_res = candidate, cand_train
            status("accepted", f"Accepted v{spec.version} (train improved).")
            test_res = evaluate(spec, schema_ddl, test, sandbox, candidate_model, "test",
                                item_reporter(spec.version))
            on_event({"type": "version", "version": spec.version,
                      "train": train_res.score, "test": test_res.score})
            log_and_announce(test_res)
            train_name = log_and_announce(train_res)            # refresh: introspection reads the new train failures
            if test_res.score > best[1].score:
                best = (spec, test_res)
            no_improve = 0
            history.append((spec.version, train_res.score, test_res.score))
        else:                                                  # reject + revert (spec unchanged)
            no_improve += 1
            status("rejected", f"Rejected v{candidate.version} (no train improvement); reverting.")
            on_event({"type": "rejected", "version": candidate.version})
            if no_improve >= config.patience:
                break

    status("promoting", f"Promoting best spec v{best[0].version}.")
    on_event({"type": "promoted", "version": best[0].version, "test": best[1].score})
    on_event({"type": "run_complete", "best_version": best[0].version,
              "best_test": best[1].score, "db_id": db_id})
    status("done", "Run complete.")
    return best, history
