import json

from crucible.types import CandidateSpec, EvalItem, Hypothesis, ItemResult
from crucible.mutation import (
    apply_hypothesis,
    classify_failure,
    pick_top_cluster,
    propose_mutation,
)


def _r(gold, pred, error=None):
    item = EvalItem("q", gold, "world_1", "medium")
    return ItemResult(item, pred, is_match=False, error=error)


def test_missing_column_error_is_schema_column():
    assert classify_failure(_r("SELECT name FROM city", "SELECT nope FROM city",
                               error="no such column: nope")) == "schema_column"


def test_missing_join_is_join():
    assert classify_failure(_r("SELECT a FROM x JOIN y ON x.i=y.i", "SELECT a FROM x")) == "join"


def test_aggregation_failure():
    assert classify_failure(_r("SELECT count(*) FROM city", "SELECT name FROM city")) == "aggregation"


def test_pick_top_cluster_returns_most_common():
    rows = [
        _r("SELECT a FROM x JOIN y ON x.i=y.i", "SELECT a FROM x"),     # join
        _r("SELECT b FROM x JOIN z ON x.i=z.i", "SELECT b FROM x"),     # join
        _r("SELECT count(*) FROM city", "SELECT name FROM city"),       # aggregation
    ]
    classified = [r.__class__(r.item, r.predicted_sql, False, r.error, classify_failure(r)) for r in rows]
    assert pick_top_cluster(classified) == "join"


def test_propose_mutation_parses_model_json():
    spec = CandidateSpec(version=1, system_prompt="Base.")
    model = lambda prompt: json.dumps({
        "rationale": "JOINs missing",
        "instruction_add": "Always join via foreign keys.",
        "few_shots": [["List capitals", "SELECT name FROM city JOIN country ..."]],
    })
    hyp = propose_mutation(spec, category="join", failing_examples=[], model=model, mcp_summary="")
    assert hyp.category == "join"
    assert "foreign keys" in hyp.instruction_add
    assert hyp.few_shots[0][0] == "List capitals"


def test_apply_hypothesis_bumps_version_and_appends():
    spec = CandidateSpec(version=2, system_prompt="Base.", few_shots=(("a", "SELECT 1"),))
    hyp = Hypothesis(category="join", rationale="x",
                     instruction_add="Join via FKs.", few_shots=(("b", "SELECT 2"),))
    new = apply_hypothesis(spec, hyp)
    assert new.version == 3
    assert "Join via FKs." in new.system_prompt
    assert len(new.few_shots) == 2          # appended, not replaced
    assert spec.version == 2                 # original unchanged (immutable)
