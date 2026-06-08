"""Candidate text-to-SQL agent: render a prompt from a spec, run it, extract the SQL.

The model is injected (ModelFn from the shared contract) so this is testable with fakes.
"""
import re

from crucible.types import CandidateSpec, EvalItem, ModelFn

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_sql(text: str) -> str:
    m = _FENCE.search(text)
    return (m.group(1) if m else text).strip()


def render_prompt(spec: CandidateSpec, schema_ddl: str, question: str) -> str:
    parts = [spec.system_prompt]
    if spec.enable_schema:
        parts.append("Database schema:\n" + schema_ddl)
    for q, sql in spec.few_shots:
        parts.append(f"Q: {q}\nSQL: {sql}")
    parts.append(f"Q: {question}\nSQL:")
    return "\n\n".join(parts)


def run_candidate_on_item(spec: CandidateSpec, schema_ddl: str, item: EvalItem, model: ModelFn) -> str:
    raw = model(render_prompt(spec, schema_ddl, item.question))
    return extract_sql(raw)
