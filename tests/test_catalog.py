"""Tests for the bundled-database catalog (crucible.datasets.catalog).

Verifies the registry shape, that every hand-authored gold SQL really executes
against its bundled SQLite database, and that the train/test splits are non-empty.
These are the guarantees the live loop relies on: if a gold query is broken the
score would be silently skewed, so we assert real execution here.
"""
from __future__ import annotations

import pytest

from crucible.datasets import catalog
from crucible.sandbox import SqlSandbox

_LIVE_DB_IDS = ["concert_singer", "university", "ecommerce"]
_ALL_DB_IDS = ["world"] + _LIVE_DB_IDS


def test_catalog_lists_world_plus_three_live_dbs():
    payload = catalog.catalog_payload()
    ids = [d["id"] for d in payload["databases"]]
    assert ids[0] == "world"
    assert set(ids) == set(_ALL_DB_IDS)


def test_world_is_demo_others_are_live():
    assert catalog.get_mode("world") == "demo"
    for db_id in _LIVE_DB_IDS:
        assert catalog.get_mode(db_id) == "live"


def test_descriptor_shape_matches_contract():
    for d in catalog.catalog_payload()["databases"]:
        assert set(d) == {
            "id", "name", "domain", "tables",
            "num_questions", "mode", "blurb",
        }
        assert isinstance(d["tables"], list) and d["tables"]
        assert d["num_questions"] == len(d["tables"]) or d["num_questions"] >= 8
        assert d["mode"] in {"demo", "live"}


@pytest.mark.parametrize("db_id", _ALL_DB_IDS)
def test_splits_non_empty(db_id):
    train, test = catalog.get_items(db_id)
    assert train, f"{db_id} train split is empty"
    assert test, f"{db_id} test split is empty"


@pytest.mark.parametrize("db_id", _ALL_DB_IDS)
def test_num_questions_matches_splits(db_id):
    train, test = catalog.get_items(db_id)
    assert catalog.get_descriptor(db_id).num_questions == len(train) + len(test)


@pytest.mark.parametrize("db_id", _ALL_DB_IDS)
def test_every_gold_sql_executes(db_id, tmp_path):
    """Every gold SQL in every split must run against the bundled DB."""
    db_path = catalog.build_db(db_id, target_dir=str(tmp_path))
    sandbox = SqlSandbox(db_path)
    train, test = catalog.get_items(db_id)
    failures = []
    for split, items in (("train", train), ("test", test)):
        for item in items:
            rows, err = sandbox.run(item.gold_sql)
            if err is not None:
                failures.append((split, item.question, err))
    assert not failures, f"{db_id} has non-executing gold SQL: {failures}"


@pytest.mark.parametrize("db_id", _LIVE_DB_IDS)
def test_live_dbs_cover_required_sql_patterns(db_id):
    """Each live DB exercises JOIN, GROUP BY/HAVING, ORDER BY+LIMIT, and subquery."""
    train, test = catalog.get_items(db_id)
    all_sql = " ".join(i.gold_sql.lower() for i in train + test)
    assert " join " in all_sql
    assert "group by" in all_sql
    assert "having" in all_sql
    assert "order by" in all_sql and "limit" in all_sql
    assert "(select" in all_sql.replace(" ", "")  # a subquery somewhere


def test_get_schema_returns_create_table_ddl():
    for db_id in _ALL_DB_IDS:
        ddl = catalog.get_schema(db_id)
        assert "CREATE TABLE" in ddl


def test_is_known_and_unknown():
    assert catalog.is_known("world")
    assert not catalog.is_known("does_not_exist")
