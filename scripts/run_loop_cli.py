"""End-to-end reflexive loop on a real DB, with live Gemini + Phoenix + MCP.

Drives ``crucible.orchestrator.run_loop`` over the ``world_1`` Spider database:
loads the dev questions for that schema, samples a difficulty-weighted pool,
splits it into train/test, then optimizes a text-to-SQL candidate spec round by
round. Each round the agent reads its own failing experiment via the Phoenix MCP
introspection seam, the mutation engine forms one hypothesis, and the candidate
is re-scored. The held-out test split is the headline number.

Run: ``uv run python scripts/run_loop_cli.py``

Requires a populated ``.env`` (PHOENIX_* + GOOGLE_* keys) and Spider data placed
at the paths in ``CRUCIBLE_DB_PATH`` / ``CRUCIBLE_SPIDER_DEV`` (see data/README.md).

Expected: per-version events printed, a climbing test score, and a final
``BEST`` + ``HISTORY`` summary; experiments and traces appear in the Phoenix UI.
"""
from __future__ import annotations

import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()

from crucible.candidate import ModelFn
from crucible.datasets.spider_loader import load_spider_dev
from crucible.datasets.split import stratified_split, weighted_sample
from crucible.mcp_introspect import introspect_failures
from crucible.models import gemini_model
from crucible.orchestrator import LoopConfig, run_loop
from crucible.phoenix_client import init_tracing, log_experiment
from crucible.sandbox import SqlSandbox
from crucible.types import CandidateSpec

# The schema this CLI optimizes against. world_1 is the canonical Spider demo DB.
DB_ID = "world_1"

# Sampling + split shape (see crucible.datasets.split for the difficulty weights).
SAMPLE_SIZE = 70
TEST_FRACTION = 0.43
SEED = 0

# v1 baseline: schema on, no few-shots (the loop earns few-shots via mutations).
INITIAL_SYSTEM_PROMPT = "You are an expert SQLite analyst. Output only SQL."

# Stopping guardrails for the optimization loop.
MAX_ITERS = 5
TARGET_SCORE = 0.9
PATIENCE = 2


def read_schema(db_path: str) -> str:
    """Return the concatenated CREATE TABLE DDL for a SQLite database.

    Opens the DB read-only and gathers every table's ``sql`` from
    ``sqlite_master`` (skipping rows where ``sql`` is NULL, e.g. internal/auto
    indexes). The result is fed to the candidate prompt as schema context.

    Args:
        db_path: Filesystem path to the SQLite database file.

    Returns:
        Newline-joined DDL string for all user tables.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    return "\n".join(row[0] for row in rows)


def main() -> None:
    """Run the end-to-end optimization loop on ``world_1`` and print results."""
    init_tracing()

    db_path = os.environ["CRUCIBLE_DB_PATH"]
    spider_dev = os.environ["CRUCIBLE_SPIDER_DEV"]

    schema = read_schema(db_path)
    items = load_spider_dev(spider_dev, db_id=DB_ID)
    pool = weighted_sample(items, n=SAMPLE_SIZE, seed=SEED)
    train, test = stratified_split(pool, test_frac=TEST_FRACTION, seed=SEED)

    model: ModelFn = gemini_model()

    best, history = run_loop(
        CandidateSpec(1, INITIAL_SYSTEM_PROMPT, enable_schema=True),
        schema,
        train,
        test,
        SqlSandbox(db_path),
        candidate_model=model,
        mutation_model=model,
        introspect=introspect_failures,
        log_experiment=log_experiment,
        on_event=print,
        db_id=DB_ID,
        config=LoopConfig(max_iters=MAX_ITERS, target=TARGET_SCORE, patience=PATIENCE),
    )

    best_spec, best_test = best
    print("BEST:", best_spec.version, "test score:", best_test.score)
    print("HISTORY:", history)


if __name__ == "__main__":
    main()
