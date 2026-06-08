#!/usr/bin/env python
"""Credential-free, fully offline demo of Crucible's reflexive optimization loop.

This script runs the REAL `crucible.orchestrator.run_loop` against a REAL SQLite
database with REAL SQL execution through the REAL `SqlSandbox`. The ONLY thing
faked is the LLM seam (`ModelFn`): instead of calling live Gemini, we inject two
deterministic, scripted stand-ins:

  * a SCRIPTED CANDIDATE MODEL that emulates a text-to-SQL agent which starts out
    weak on harder questions (JOIN / GROUP BY / ORDER BY) and gets STRONGER as the
    optimizer injects relevant few-shots and instructions into its prompt, and
  * a SCRIPTED MUTATION MODEL that, for the current dominant failure cluster,
    returns a JSON mutation whose few-shots / instruction carry the marker
    substrings that flip the candidate to correct SQL for that cluster.

Net effect: v1 scores ~50-60% on the held-out test split, then the loop accepts
mutations and the test score climbs to >= ~90-100% over a couple of rounds. The
climb is genuine — every score is the result of executing predicted SQL against
the real database and comparing result sets to gold.

Run it:  uv run python scripts/offline_demo.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

# This repo uses a src-layout and is not installed as a package (tests rely on
# pytest's `pythonpath = ["src"]`). For a standalone `uv run` script we put the
# same `src` directory on the import path so `crucible.*` resolves.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from crucible.orchestrator import LoopConfig, run_loop  # noqa: E402
from crucible.sandbox import SqlSandbox  # noqa: E402
from crucible.types import CandidateSpec, EvalItem, EvalResult  # noqa: E402

# ---------------------------------------------------------------------------
# Marker substrings. These are the levers the demo turns on.
#
# The scripted MUTATION model injects these markers into the candidate's prompt
# (via an instruction line and/or few-shots). The scripted CANDIDATE model
# detects them in its incoming prompt and, when present, switches from a
# deliberately-wrong answer to the correct SQL for the matching failure cluster.
#
# This mirrors how a real LLM-driven agent improves once its prompt gains a
# relevant few-shot: nothing here is special-cased outside the prompt text.
# ---------------------------------------------------------------------------
MARKER_JOIN = "USE_JOIN"
MARKER_AGG = "USE_GROUP_BY"
MARKER_ORDER = "USE_ORDER_BY"

DB_ID = "world"


# ---------------------------------------------------------------------------
# 1. Build a real SQLite "world"-style database in a temp dir.
# ---------------------------------------------------------------------------
SCHEMA_DDL = """\
CREATE TABLE country (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    continent   TEXT NOT NULL,
    population  INTEGER NOT NULL
);
CREATE TABLE city (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    country_code TEXT NOT NULL REFERENCES country(code),
    population   INTEGER NOT NULL
);
CREATE TABLE countrylanguage (
    country_code TEXT NOT NULL REFERENCES country(code),
    language     TEXT NOT NULL,
    is_official  INTEGER NOT NULL
);"""

_COUNTRIES = [
    ("USA", "United States", "North America", 331_000_000),
    ("CHN", "China", "Asia", 1_412_000_000),
    ("IND", "India", "Asia", 1_408_000_000),
    ("BRA", "Brazil", "South America", 214_000_000),
    ("FRA", "France", "Europe", 67_000_000),
    ("DEU", "Germany", "Europe", 83_000_000),
    ("JPN", "Japan", "Asia", 125_000_000),
]

_CITIES = [
    (1, "New York", "USA", 8_336_000),
    (2, "Los Angeles", "USA", 3_980_000),
    (3, "Shanghai", "CHN", 24_870_000),
    (4, "Beijing", "CHN", 21_540_000),
    (5, "Mumbai", "IND", 12_440_000),
    (6, "Delhi", "IND", 16_790_000),
    (7, "Sao Paulo", "BRA", 12_330_000),
    (8, "Paris", "FRA", 2_160_000),
    (9, "Berlin", "DEU", 3_640_000),
    (10, "Tokyo", "JPN", 13_960_000),
]

_LANGUAGES = [
    ("USA", "English", 1),
    ("CHN", "Mandarin", 1),
    ("IND", "Hindi", 1),
    ("IND", "English", 1),
    ("BRA", "Portuguese", 1),
    ("FRA", "French", 1),
    ("DEU", "German", 1),
    ("JPN", "Japanese", 1),
]


def build_database(db_path: Path) -> None:
    """Create and populate the demo SQLite database with realistic rows."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_DDL)
        conn.executemany("INSERT INTO country VALUES (?, ?, ?, ?)", _COUNTRIES)
        conn.executemany("INSERT INTO city VALUES (?, ?, ?, ?)", _CITIES)
        conn.executemany("INSERT INTO countrylanguage VALUES (?, ?, ?)", _LANGUAGES)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. Hand-authored eval items (NL question + gold SQL), split train / test.
#
# Each item carries an "intent" tag we reuse in the scripted candidate model so
# it knows which answer to produce. The gold SQL all runs on the database above.
# ---------------------------------------------------------------------------
# We attach the intent via the question wording itself (the candidate matches on
# the exact question string), so EvalItem stays the plain shared contract type.

# (question, gold_sql, difficulty)
_EASY = [
    ("List all country names.",
     "SELECT name FROM country", "easy"),
    ("What is the population of France?",
     "SELECT population FROM country WHERE name = 'France'", "easy"),
    ("How many countries are there?",
     "SELECT COUNT(*) FROM country", "easy"),
    ("Which countries are in Europe?",
     "SELECT name FROM country WHERE continent = 'Europe'", "easy"),
]

# JOIN cluster: needs a city -> country join.
_JOIN = [
    ("List each city name with its country name.",
     "SELECT city.name, country.name FROM city "
     "JOIN country ON city.country_code = country.code", "hard"),
    ("Which cities are in Asia?",
     "SELECT city.name FROM city "
     "JOIN country ON city.country_code = country.code "
     "WHERE country.continent = 'Asia'", "hard"),
]

# Aggregation cluster: needs GROUP BY. Single-table so the failure classifies
# as "aggregation" (a JOIN in the gold would be classified as "join" first).
_AGG = [
    ("How many cities are in each country code?",
     "SELECT country_code, COUNT(*) FROM city GROUP BY country_code", "hard"),
]

# Ordering cluster: needs ORDER BY.
_ORDER = [
    ("List country names ordered by population descending.",
     "SELECT name FROM country ORDER BY population DESC", "medium"),
    ("List city names ordered by population descending.",
     "SELECT name FROM city ORDER BY population DESC", "medium"),
]


def _items(rows: list[tuple[str, str, str]]) -> list[EvalItem]:
    return [EvalItem(q, sql, DB_ID, diff) for q, sql, diff in rows]


# Train (5): 2 easy, 1 join, 1 agg, 1 order — exercises every cluster.
TRAIN: list[EvalItem] = (
    _items(_EASY[:2]) + _items(_JOIN[:1]) + _items(_AGG[:1]) + _items(_ORDER[:1])
)
# Test (4, held out): 2 easy, 1 join, 1 order. With 2 of 4 items in unfixed
# clusters at v1 the demo starts ~50% and climbs to 100% as clusters unlock.
TEST: list[EvalItem] = (
    _items(_EASY[2:4]) + _items(_JOIN[1:2]) + _items(_ORDER[1:2])
)


# ---------------------------------------------------------------------------
# 3. Scripted CANDIDATE model — a deterministic stand-in for Gemini.
#
# It receives the fully rendered prompt (system prompt + schema + few-shots +
# the final "Q: <question>\nSQL:"). It:
#   - finds the final question (the last "Q:" before the trailing "SQL:"),
#   - looks at WHICH marker substrings are present elsewhere in the prompt
#     (these are injected by accepted mutations), and
#   - returns correct SQL for "hard" clusters ONLY once the relevant marker is
#     present; otherwise it returns a deliberately-wrong baseline answer.
#
# Easy questions are always answered correctly. This makes v1 partially correct
# and lets the score climb as clusters get unlocked.
# ---------------------------------------------------------------------------
def _final_question(prompt: str) -> str:
    """Extract the target question: the last 'Q: ...' line in the prompt."""
    last_q = prompt.rfind("Q:")
    tail = prompt[last_q + 2:]
    # The question runs up to the 'SQL:' marker that follows it.
    sql_idx = tail.find("SQL:")
    question = tail[:sql_idx] if sql_idx != -1 else tail
    return question.strip()


def _context(prompt: str, question: str) -> str:
    """The prompt minus the final question line — where injected markers live."""
    return prompt.replace(question, "", 1)


def make_candidate_model():
    """Return a deterministic candidate ModelFn.

    Behavior per question (correct SQL is wrapped in a ```sql fence so the real
    `extract_sql` path is exercised):
      * easy items: always correct.
      * JOIN items: wrong (no JOIN) until MARKER_JOIN appears in the prompt.
      * AGG items: wrong (no GROUP BY) until MARKER_AGG appears.
      * ORDER items: wrong (no ORDER BY) until MARKER_ORDER appears.
    """

    def fence(sql: str) -> str:
        return f"```sql\n{sql}\n```"

    def candidate_model(prompt: str) -> str:
        question = _final_question(prompt)
        context = _context(prompt, question)

        # --- easy cluster: always correct ---
        if question == "List all country names.":
            return fence("SELECT name FROM country")
        if question == "What is the population of France?":
            return fence("SELECT population FROM country WHERE name = 'France'")
        if question == "How many countries are there?":
            return fence("SELECT COUNT(*) FROM country")
        if question == "Which countries are in Europe?":
            return fence("SELECT name FROM country WHERE continent = 'Europe'")

        # --- JOIN cluster ---
        if question == "List each city name with its country name.":
            if MARKER_JOIN in context:
                return fence(
                    "SELECT city.name, country.name FROM city "
                    "JOIN country ON city.country_code = country.code"
                )
            # Wrong: ignores the join, returns city names only (wrong shape).
            return fence("SELECT name FROM city")
        if question == "Which cities are in Asia?":
            if MARKER_JOIN in context:
                return fence(
                    "SELECT city.name FROM city "
                    "JOIN country ON city.country_code = country.code "
                    "WHERE country.continent = 'Asia'"
                )
            # Wrong: filters city table on a column that yields nothing useful.
            return fence("SELECT name FROM city WHERE country_code = 'Asia'")

        # --- aggregation cluster ---
        if question == "How many cities are in each country code?":
            if MARKER_AGG in context:
                return fence(
                    "SELECT country_code, COUNT(*) FROM city "
                    "GROUP BY country_code"
                )
            # Wrong: a single total instead of a per-group breakdown.
            return fence("SELECT COUNT(*) FROM city")

        # --- ordering cluster ---
        if question == "List country names ordered by population descending.":
            if MARKER_ORDER in context:
                return fence("SELECT name FROM country ORDER BY population DESC")
            # Wrong: ignores ORDER BY (rows come back in a different order).
            return fence("SELECT name FROM country")
        if question == "List city names ordered by population descending.":
            if MARKER_ORDER in context:
                return fence("SELECT name FROM city ORDER BY population DESC")
            # Wrong: ignores ORDER BY.
            return fence("SELECT name FROM city")

        # Unknown question: harmless valid SQL (counts as a miss against gold).
        return fence("SELECT 1")

    return candidate_model


# ---------------------------------------------------------------------------
# 4. Scripted MUTATION model — a deterministic stand-in for Gemini.
#
# `propose_mutation` formats a prompt that contains "The dominant failure
# category is: <category>." We read that category and return a JSON mutation
# whose instruction + few-shots embed the marker that unlocks the candidate for
# that cluster. The categories come from `mutation.classify_failure`:
#   join -> "join", aggregation -> "aggregation", ordering -> "ordering".
# ---------------------------------------------------------------------------
_CLUSTER_FIX: dict[str, dict] = {
    "join": {
        "rationale": "Failing items need rows from two tables; teach an explicit JOIN.",
        "instruction_add": f"When a question spans tables, {MARKER_JOIN}: "
                           "join on the foreign key (city.country_code = country.code).",
        "few_shots": [[
            "List each city name with its country name.",
            f"-- {MARKER_JOIN}\nSELECT city.name, country.name FROM city "
            "JOIN country ON city.country_code = country.code",
        ]],
    },
    "aggregation": {
        "rationale": "Per-group counts need GROUP BY, not a single total.",
        "instruction_add": f"For per-group counts, {MARKER_AGG}: "
                           "group by the grouping column.",
        "few_shots": [[
            "How many cities are in each country code?",
            f"-- {MARKER_AGG}\nSELECT country_code, COUNT(*) FROM city "
            "GROUP BY country_code",
        ]],
    },
    "ordering": {
        "rationale": "Ranked questions must preserve order with ORDER BY.",
        "instruction_add": f"When a question asks for an order, {MARKER_ORDER}: "
                           "add ORDER BY on the relevant column.",
        "few_shots": [[
            "List country names ordered by population descending.",
            f"-- {MARKER_ORDER}\nSELECT name FROM country ORDER BY population DESC",
        ]],
    },
}


def make_mutation_model():
    """Return a deterministic mutation ModelFn that emits marker-bearing JSON."""

    def _category_from_prompt(prompt: str) -> str:
        marker = "dominant failure category is: "
        start = prompt.find(marker)
        if start == -1:
            return "join"
        start += len(marker)
        end = prompt.find(".", start)
        return prompt[start:end].strip() if end != -1 else prompt[start:].strip()

    def mutation_model(prompt: str) -> str:
        category = _category_from_prompt(prompt)
        fix = _CLUSTER_FIX.get(category, _CLUSTER_FIX["join"])
        return json.dumps(fix)

    return mutation_model


# ---------------------------------------------------------------------------
# 5. introspect + log_experiment (offline, no network).
# ---------------------------------------------------------------------------
def introspect(experiment_name: str) -> str:
    """Stand-in for the MCP trace read; offline it returns a fixed summary."""
    return f"(offline) read failing traces locally for {experiment_name}"


def log_experiment(result: EvalResult, db_id: str) -> str:
    """Stand-in for the experiment logger; returns a stable identifier."""
    return f"{db_id}-v{result.spec_version}-{result.split}"


# ---------------------------------------------------------------------------
# 6. on_event — a live, readable leaderboard printed as the loop runs.
# ---------------------------------------------------------------------------
def _pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def make_event_printer():
    """Return an on_event callback that pretty-prints each loop event."""
    state = {"best_test": 0.0}

    def on_event(event: dict) -> None:
        kind = event["type"]
        if kind == "version":
            test = event["test"]
            arrow = ""
            if test > state["best_test"]:
                arrow = "  NEW BEST"
                state["best_test"] = test
            bar = "#" * round(test * 20)
            print(
                f"  v{event['version']:<2d} | train {_pct(event['train'])} "
                f"| test {_pct(test)} | {bar:<20}{arrow}"
            )
        elif kind == "hypothesis":
            print(f"       -> failing cluster: '{event['category']}'  "
                  f"({event['mcp_summary']})")
            print(f"          proposing one atomic mutation to fix it ...")
        elif kind == "rejected":
            print(f"       x  candidate v{event['version']} rejected "
                  f"(no train improvement) — reverted")
        elif kind == "promoted":
            print("-" * 60)
            print(f"  PROMOTED best spec: v{event['version']} "
                  f"| test {_pct(event['test'])}")

    return on_event


# ---------------------------------------------------------------------------
# 7. Wire it all together and run the REAL loop.
# ---------------------------------------------------------------------------
def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "world.sqlite"
        build_database(db_path)
        sandbox = SqlSandbox(str(db_path))

        initial_spec = CandidateSpec(
            version=1,
            system_prompt="You are an expert SQLite analyst. Output only SQL.",
            enable_schema=True,
        )
        config = LoopConfig(max_iters=5, target=0.9, patience=2)

        print("=" * 60)
        print("  Crucible — OFFLINE reflexive optimization demo")
        print("  Real SQLite + real SQL execution + scripted (no-API) model")
        print("=" * 60)
        print(f"  DB: {db_path}")
        print(f"  Train items: {len(TRAIN)}   Test items (held out): {len(TEST)}")
        print(f"  Target test score: {_pct(config.target)}   "
              f"max_iters: {config.max_iters}   patience: {config.patience}")
        print("-" * 60)
        print("  Leaderboard (each line = an accepted spec version):")
        print("-" * 60)

        (best_spec, best_res), history = run_loop(
            initial_spec=initial_spec,
            schema_ddl=SCHEMA_DDL,
            train=TRAIN,
            test=TEST,
            sandbox=sandbox,
            candidate_model=make_candidate_model(),
            mutation_model=make_mutation_model(),
            introspect=introspect,
            log_experiment=log_experiment,
            on_event=make_event_printer(),
            db_id=DB_ID,
            config=config,
        )

        first_test = history[0][2]
        print()
        print("=" * 60)
        print("  RESULT")
        print("=" * 60)
        print(f"  Starting test score (v{history[0][0]}): {_pct(first_test)}")
        print(f"  Best spec version:                  v{best_spec.version}")
        print(f"  Best held-out test score:           {_pct(best_res.score)}")
        accepted = max(0, len(history) - 1)
        print(f"  Accepted mutations:                 {accepted}")
        print(f"  Climb:                              "
              f"{_pct(first_test)} -> {_pct(best_res.score)}")
        print("=" * 60)


if __name__ == "__main__":
    main()
