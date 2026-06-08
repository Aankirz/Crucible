"""Run the loop offline on extra DBs and save leaderboards for the demo.

Proves generality: the same reflexive optimization loop that runs live on
``world_1`` (see ``scripts/run_loop_cli.py``) is run here on two additional
schemas (one extra Spider DB + one BIRD financial DB) and their climbs are
persisted to ``data/prebaked_results.json`` for the demo results table.

Run: ``uv run python scripts/run_prebaked.py``

Requires a populated ``.env`` (PHOENIX_* + GOOGLE_* keys) and each target's
SQLite file + matching dev questions placed per ``data/README.md``.

Output: ``data/prebaked_results.json`` mapping ``{db_id: {final_test, history}}``.
"""
from __future__ import annotations

import json
import os

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

# Reuse the read-only schema reader from the live CLI so both paths stay in sync.
from scripts.run_loop_cli import read_schema

# (db_id, sqlite_path) — two additional schemas beyond the live world_1 demo:
# one extra Spider DB and one BIRD financial DB. db_id must match the db_id used
# in the dev questions file (CRUCIBLE_SPIDER_DEV) so loading filters correctly.
TARGETS: list[tuple[str, str]] = [
    ("concert_singer", "data/concert_singer/concert_singer.sqlite"),
    ("financial", "data/bird/financial/financial.sqlite"),
]

# Output path for the demo results table.
RESULTS_PATH = "data/prebaked_results.json"

# Sampling + split shape (slightly smaller pool than the live run, for speed).
SAMPLE_SIZE = 60
TEST_FRACTION = 0.43
SEED = 0

# v1 baseline matches the live CLI: schema on, no few-shots.
INITIAL_SYSTEM_PROMPT = "You are an expert SQLite analyst. Output only SQL."

# Stopping guardrails (identical to the live run for comparable leaderboards).
MAX_ITERS = 5
TARGET_SCORE = 0.9
PATIENCE = 2


def _run_one(db_id: str, sqlite_path: str, model: ModelFn) -> dict:
    """Optimize one DB and return its ``{final_test, history}`` summary."""
    spider_dev = os.environ["CRUCIBLE_SPIDER_DEV"]
    items = load_spider_dev(spider_dev, db_id=db_id)
    pool = weighted_sample(items, n=SAMPLE_SIZE, seed=SEED)
    train, test = stratified_split(pool, test_frac=TEST_FRACTION, seed=SEED)

    best, history = run_loop(
        CandidateSpec(1, INITIAL_SYSTEM_PROMPT, enable_schema=True),
        read_schema(sqlite_path),
        train,
        test,
        SqlSandbox(sqlite_path),
        candidate_model=model,
        mutation_model=model,
        introspect=introspect_failures,
        log_experiment=log_experiment,
        on_event=lambda event: None,
        db_id=db_id,
        config=LoopConfig(max_iters=MAX_ITERS, target=TARGET_SCORE, patience=PATIENCE),
    )
    return {"final_test": best[1].score, "history": history}


def main() -> None:
    """Run the loop on every target DB and write the combined results file."""
    init_tracing()
    model: ModelFn = gemini_model()

    results: dict[str, dict] = {}
    for db_id, sqlite_path in TARGETS:
        results[db_id] = _run_one(db_id, sqlite_path, model)

    with open(RESULTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)

    print(results)


if __name__ == "__main__":
    main()
