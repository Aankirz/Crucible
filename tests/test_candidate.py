from crucible.types import CandidateSpec, EvalItem
from crucible.candidate import render_prompt, extract_sql, run_candidate_on_item

SCHEMA = "CREATE TABLE city(name TEXT, pop INT);"


def test_render_includes_schema_and_fewshots_when_enabled():
    spec = CandidateSpec(
        version=2,
        system_prompt="You write SQLite SQL.",
        few_shots=(("How many cities?", "SELECT count(*) FROM city"),),
        enable_schema=True,
    )
    prompt = render_prompt(spec, SCHEMA, "List city names")
    assert "CREATE TABLE city" in prompt
    assert "SELECT count(*) FROM city" in prompt
    assert prompt.strip().endswith("SQL:")


def test_render_omits_schema_when_disabled():
    spec = CandidateSpec(version=1, system_prompt="x", enable_schema=False)
    assert "CREATE TABLE" not in render_prompt(spec, SCHEMA, "q")


def test_extract_sql_strips_code_fence():
    assert extract_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert extract_sql("SELECT 2") == "SELECT 2"


def test_run_candidate_uses_injected_model():
    spec = CandidateSpec(version=1, system_prompt="x")
    item = EvalItem("List names", "SELECT name FROM city", "world_1", "easy")
    fake_model = lambda prompt: "```sql\nSELECT name FROM city\n```"
    assert run_candidate_on_item(spec, SCHEMA, item, fake_model) == "SELECT name FROM city"
