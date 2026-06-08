"""LIVE end-to-end demo: the real reflexive loop driven by real Gemini 3.

Unlike scripts/offline_demo.py (deterministic scripted model), this runs the actual
`crucible.models.gemini_model()` against the live Gemini API on a self-contained real
SQLite "world" database with human-authored gold SQL. Phoenix is stubbed here (no creds
required for this script); the full Phoenix+MCP path lives in scripts/run_loop_cli.py.

Run: uv run python scripts/live_gemini_demo.py   (requires GOOGLE_API_KEY in .env)

NOTE on quotas (observed 2026-06-09): the Gemini free tier caps a project at ~20
generate_content requests/day. A full loop here makes ~30-40 calls, so a complete
multi-iteration live run needs either billing enabled or a budgeted tiny set
(shrink TRAIN/TEST + LoopConfig.max_iters=1) to stay under the daily cap. The
mechanical proof of the loop climbing on real SQL is in scripts/offline_demo.py.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from crucible.candidate import run_candidate_on_item  # noqa: E402
from crucible.models import gemini_model  # noqa: E402
from crucible.orchestrator import LoopConfig, run_loop  # noqa: E402
from crucible.sandbox import SqlSandbox  # noqa: E402
from crucible.types import CandidateSpec, EvalItem  # noqa: E402

SCHEMA = """
CREATE TABLE country (
    code TEXT PRIMARY KEY, name TEXT, continent TEXT, population INTEGER
);
CREATE TABLE city (
    id INTEGER PRIMARY KEY, name TEXT, country_code TEXT, population INTEGER
);
CREATE TABLE countrylanguage (
    country_code TEXT, language TEXT, is_official INTEGER
);
"""

ROWS = """
INSERT INTO country VALUES
  ('IND','India','Asia',1400000000),
  ('CHN','China','Asia',1410000000),
  ('USA','United States','North America',331000000),
  ('BRA','Brazil','South America',213000000),
  ('FRA','France','Europe',67000000);
INSERT INTO city VALUES
  (1,'Mumbai','IND',12400000),(2,'Delhi','IND',16700000),
  (3,'Shanghai','CHN',24800000),(4,'Beijing','CHN',21500000),
  (5,'New York','USA',8400000),(6,'Sao Paulo','BRA',12300000),
  (7,'Paris','FRA',2100000);
INSERT INTO countrylanguage VALUES
  ('IND','Hindi',1),('IND','English',1),('CHN','Mandarin',1),
  ('USA','English',1),('BRA','Portuguese',1),('FRA','French',1),('FRA','Breton',0);
"""

# Human-authored gold SQL. Train and test share PATTERNS (HAVING, ORDER BY+LIMIT,
# subquery) so a fix the loop learns on a train failure can generalize to held-out test.
TRAIN = [
    EvalItem("How many countries are there?",
             "SELECT count(*) FROM country", "world", "easy"),
    EvalItem("List each city name along with the name of its country.",
             "SELECT city.name, country.name FROM city "
             "JOIN country ON city.country_code=country.code", "world", "medium"),
    EvalItem("How many cities does each country have? Return country code and the count.",
             "SELECT country_code, count(*) FROM city GROUP BY country_code", "world", "medium"),
    # HAVING pattern
    EvalItem("Which countries have more than one city? Return the country name.",
             "SELECT country.name FROM city JOIN country ON city.country_code=country.code "
             "GROUP BY country.code HAVING count(*) > 1", "world", "hard"),
    # ORDER BY + LIMIT pattern
    EvalItem("Which country has the most cities? Return its name.",
             "SELECT country.name FROM city JOIN country ON city.country_code=country.code "
             "GROUP BY country.code ORDER BY count(*) DESC LIMIT 1", "world", "hard"),
    # subquery pattern
    EvalItem("List the names of cities whose population is above the average city population.",
             "SELECT name FROM city WHERE population > (SELECT avg(population) FROM city)",
             "world", "hard"),
]

TEST = [   # held-out: same patterns as train, different questions -> measures generalization
    EvalItem("List the names of countries in Asia.",
             "SELECT name FROM country WHERE continent='Asia'", "world", "easy"),
    # HAVING pattern (on languages)
    EvalItem("Which countries have more than one official language? Return the country code.",
             "SELECT country_code FROM countrylanguage WHERE is_official=1 "
             "GROUP BY country_code HAVING count(*) > 1", "world", "hard"),
    # ORDER BY + LIMIT pattern (on population)
    EvalItem("What is the name of the country with the largest population?",
             "SELECT name FROM country ORDER BY population DESC LIMIT 1", "world", "hard"),
    # subquery pattern (on countries)
    EvalItem("List the names of countries whose population is above the average country population.",
             "SELECT name FROM country WHERE population > (SELECT avg(population) FROM country)",
             "world", "hard"),
]


def build_db() -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="crucible_live_"), "world.sqlite")
    con = sqlite3.connect(path)
    con.executescript(SCHEMA + ROWS)
    con.commit()
    con.close()
    return path


def _bar(score: float) -> str:
    return "#" * int(round(score * 20))


def on_event(e: dict) -> None:
    t = e["type"]
    if t == "version":
        print(f"  v{e['version']:<2}| train {e['train']*100:5.1f}% | "
              f"test {e['test']*100:5.1f}% | {_bar(e['test']):<20}")
    elif t == "hypothesis":
        print(f"      -> failing cluster: '{e['category']}'  (introspect: "
              f"{e['mcp_summary'] or 'deterministic fallback'})")
    elif t == "rejected":
        print(f"      x  v{e['version']} rejected (no train improvement)")
    elif t == "promoted":
        print(f"  PROMOTED v{e['version']} | held-out test {e['test']*100:.1f}%")


def main() -> None:
    db = build_db()
    model = gemini_model()
    print("=" * 60)
    print("  Crucible — LIVE demo (real Gemini 3 + real SQLite)")
    print("=" * 60)
    print(f"  model: {os.environ.get('GEMINI_MODEL')}   train: {len(TRAIN)}  "
          f"test(held-out): {len(TEST)}")
    print("-" * 60)
    best, history = run_loop(
        # v1 starts WITHOUT the schema: the model must guess table/column names and
        # genuinely fails. The loop then learns the real schema from its own failures
        # by injecting exemplars derived from the gold answers — an honest climb.
        initial_spec=CandidateSpec(
            1, "You are an expert SQLite analyst. Output only a single SQL query.",
            enable_schema=False),
        schema_ddl=SCHEMA, train=TRAIN, test=TEST,
        sandbox=SqlSandbox(db),
        candidate_model=model, mutation_model=model,
        introspect=lambda name: "",                       # Phoenix MCP stubbed here
        log_experiment=lambda result, db_id: f"{db_id}-v{result.spec_version}",
        on_event=on_event, db_id="world",
        config=LoopConfig(max_iters=3, target=0.9, patience=2),
    )
    print("-" * 60)
    print(f"  BEST v{best[0].version} | held-out test {best[1].score*100:.1f}%")
    print(f"  history (version, train, test): {history}")


if __name__ == "__main__":
    main()
