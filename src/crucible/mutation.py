"""Failure classification + cluster selection + mutation proposal.

The reflexive brain: given a candidate's failing runs, find the dominant failure
pattern, then propose ONE atomic improvement (an instruction line + targeted few-shots).
All LLM behavior flows through the injected ModelFn so this is fully unit-testable.
"""
import json
from collections import Counter

from crucible.types import CandidateSpec, Hypothesis, ItemResult, ModelFn

_AGG = ("count(", "sum(", "avg(", "max(", "min(", "group by")


def classify_failure(result: ItemResult) -> str:
    """Map a failing ItemResult to one of the fixed failure categories."""
    err = (result.error or "").lower()
    if "no such column" in err or "no such table" in err:
        return "schema_column"
    if err:
        return "syntax"
    gold = result.item.gold_sql.lower()
    pred = result.predicted_sql.lower()
    if " join " in gold and " join " not in pred:
        return "join"
    if any(a in gold for a in _AGG):
        return "aggregation"
    g_from = gold.find(" from ")
    if g_from != -1 and "select" in gold[g_from + 6:]:
        return "nested"
    if "order by" in gold:
        return "ordering"
    return "value_format"


def pick_top_cluster(results: list[ItemResult]) -> str | None:
    """Return the most common failure category among classified results, or None."""
    cats = [r.category for r in results if r.category]
    if not cats:
        return None
    return Counter(cats).most_common(1)[0][0]


_PROMPT = """You improve a text-to-SQL agent. The dominant failure category is: {category}.
MCP analysis of the agent's own traces: {mcp_summary}
Failing examples (question | gold_sql | predicted_sql):
{examples}

Propose ONE atomic improvement. Respond ONLY as JSON:
{{"rationale": "...", "instruction_add": "one instruction line", "few_shots": [["question","correct_sql"]]}}"""


def propose_mutation(spec: CandidateSpec, category: str, failing_examples: list,
                     model: ModelFn, mcp_summary: str = "") -> Hypothesis:
    """Ask the model for one atomic improvement targeting the failure category."""
    examples = "\n".join(
        f"{r.item.question} | {r.item.gold_sql} | {r.predicted_sql}" for r in failing_examples[:5]
    )
    raw = model(_PROMPT.format(category=category, mcp_summary=mcp_summary or "(none)", examples=examples))
    json_str = raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else ""
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        data = {}                                        # garbled reply -> empty hypothesis (loop treats as no-op)
    return Hypothesis(
        category=category,
        rationale=data.get("rationale", ""),
        instruction_add=data.get("instruction_add", ""),
        few_shots=tuple(tuple(fs) for fs in data.get("few_shots", [])),
    )


def apply_hypothesis(spec: CandidateSpec, hyp: Hypothesis) -> CandidateSpec:
    """Return a new spec (immutable) with the hypothesis applied: version bumped,
    instruction appended, few-shots appended (never replaced)."""
    new_prompt = spec.system_prompt
    if hyp.instruction_add:
        new_prompt = spec.system_prompt + "\n- " + hyp.instruction_add
    return CandidateSpec(
        version=spec.version + 1,
        system_prompt=new_prompt,
        few_shots=spec.few_shots + hyp.few_shots,
        enable_schema=spec.enable_schema,
        enable_validate_tool=spec.enable_validate_tool,
    )
