import sqlite3

import pytest

from crucible.types import CandidateSpec, EvalItem
from crucible.sandbox import SqlSandbox
from crucible.eval_engine import evaluate

SCHEMA = "CREATE TABLE city(name TEXT, pop INT);"


@pytest.fixture
def sandbox(tmp_path):
    p = tmp_path / "t.sqlite"
    con = sqlite3.connect(p)
    con.executescript(SCHEMA + "INSERT INTO city VALUES ('A',10),('B',20);")
    con.commit()
    con.close()
    return SqlSandbox(str(p))


def test_scores_correct_and_incorrect(sandbox):
    items = [
        EvalItem("count", "SELECT count(*) FROM city", "world_1", "easy"),            # model right
        EvalItem("names", "SELECT name FROM city ORDER BY name", "world_1", "easy"),  # model wrong
    ]
    answers = {
        "count": "SELECT count(*) FROM city",
        "names": "SELECT pop FROM city",       # wrong columns/values
    }
    model = lambda prompt: answers["count"] if "count" in prompt else answers["names"]
    res = evaluate(CandidateSpec(1, "x"), SCHEMA, items, sandbox, model, "train")
    assert res.score == 0.5
    assert res.item_results[0].is_match
    assert not res.item_results[1].is_match


def test_execution_error_scores_zero_and_records_error(sandbox):
    items = [EvalItem("q", "SELECT count(*) FROM city", "world_1", "easy")]
    model = lambda prompt: "SELECT nope FROM city"
    res = evaluate(CandidateSpec(1, "x"), SCHEMA, items, sandbox, model, "test")
    assert res.score == 0.0
    assert res.item_results[0].error is not None
