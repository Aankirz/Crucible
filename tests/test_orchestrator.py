import sqlite3

import pytest

from crucible.types import CandidateSpec, EvalItem
from crucible.sandbox import SqlSandbox
from crucible.orchestrator import run_loop, LoopConfig

SCHEMA = "CREATE TABLE city(name TEXT, pop INT);"


@pytest.fixture
def sandbox(tmp_path):
    p = tmp_path / "t.sqlite"
    con = sqlite3.connect(p)
    con.executescript(SCHEMA + "INSERT INTO city VALUES ('A',10),('B',20);")
    con.commit()
    con.close()
    return SqlSandbox(str(p))


def test_loop_improves_and_stops_at_target(sandbox):
    items = [
        EvalItem("count", "SELECT count(*) FROM city", "world_1", "easy"),
        EvalItem("names", "SELECT name FROM city ORDER BY name", "world_1", "easy"),
    ]

    # Candidate model: only answers "names" correctly AFTER a mutation injects an ORDER BY few-shot.
    def model(prompt):
        if "order by" in prompt.lower():                              # post-mutation prompt
            return ("SELECT count(*) FROM city" if "count" in prompt
                    else "SELECT name FROM city ORDER BY name")
        return ("SELECT count(*) FROM city" if "count" in prompt
                else "SELECT pop FROM city")                          # v1: wrong on "names"

    # Mutation model returns a few-shot whose SQL contains ORDER BY (flips the candidate model).
    mut_model = lambda p: ('{"rationale":"ordering","instruction_add":"Respect ORDER BY.",'
                           '"few_shots":[["names","SELECT name FROM city ORDER BY name"]]}')

    events = []
    best, history = run_loop(
        initial_spec=CandidateSpec(1, "Write SQLite SQL.", enable_schema=True),
        schema_ddl=SCHEMA, train=items, test=items,
        sandbox=sandbox, candidate_model=model, mutation_model=mut_model,
        introspect=lambda name: "",                                  # MCP stubbed in unit test
        log_experiment=lambda result, db_id: "exp",
        on_event=lambda e: events.append(("event", e["type"])),
        db_id="world_1", config=LoopConfig(max_iters=4, target=1.0, patience=2),
    )
    best_spec, best_test = best
    assert best_test.score == 1.0                  # reached target after mutation
    assert best_spec.version >= 2                   # at least one accepted mutation
    assert any(e == ("event", "promoted") for e in events)


def test_loop_early_stops_on_no_improvement(sandbox):
    items = [EvalItem("names", "SELECT name FROM city", "world_1", "easy")]
    model = lambda prompt: "SELECT pop FROM city"   # always wrong, never improves
    mut_model = lambda p: '{"rationale":"x","instruction_add":"try harder","few_shots":[]}'
    best, history = run_loop(
        initial_spec=CandidateSpec(1, "x"), schema_ddl=SCHEMA, train=items, test=items,
        sandbox=sandbox, candidate_model=model, mutation_model=mut_model,
        introspect=lambda name: "", log_experiment=lambda r, d: "exp",
        on_event=lambda e: None, db_id="world_1",
        config=LoopConfig(max_iters=10, target=1.0, patience=2),
    )
    assert len(history) <= 4                         # stopped early, not all 10 iters
