"""Shared contract for Crucible.

This is the ONE file both teams depend on. It is locked at GATE 0. Any change after
GATE 0 is a joint decision (see docs/superpowers/COORDINATION.md), not a silent edit.
"""
from collections.abc import Callable
from dataclasses import dataclass

# The single LLM seam. All model behavior (candidate SQL generation, mutation proposals)
# flows through this so the whole loop is testable with deterministic fakes (no network).
ModelFn = Callable[[str], str]   # prompt -> raw model text


@dataclass(frozen=True)
class EvalItem:
    question: str
    gold_sql: str
    db_id: str
    difficulty: str                 # "easy" | "medium" | "hard" | "extra"


@dataclass(frozen=True)
class MatchResult:
    is_match: bool
    reason: str


@dataclass(frozen=True)
class CandidateSpec:
    version: int
    system_prompt: str
    few_shots: tuple = ()           # tuple[tuple[str, str], ...] -> (question, sql)
    enable_schema: bool = True
    enable_validate_tool: bool = False


@dataclass(frozen=True)
class ItemResult:
    item: EvalItem
    predicted_sql: str
    is_match: bool
    error: str | None = None
    category: str | None = None     # failure category, set by mutation.classify_failure


@dataclass(frozen=True)
class EvalResult:
    spec_version: int
    split: str                      # "train" | "test"
    score: float
    item_results: tuple = ()        # tuple[ItemResult, ...]


@dataclass(frozen=True)
class Hypothesis:
    category: str
    rationale: str
    instruction_add: str
    few_shots: tuple = ()           # tuple[tuple[str, str], ...]
