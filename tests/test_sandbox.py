import sqlite3

import pytest

from crucible.sandbox import SqlSandbox


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "t.sqlite"
    con = sqlite3.connect(p)
    con.executescript(
        "CREATE TABLE city(name TEXT, pop INT);"
        "INSERT INTO city VALUES ('A', 10), ('B', 20);"
    )
    con.commit()
    con.close()
    return str(p)


def test_select_returns_rows(db_path):
    rows, err = SqlSandbox(db_path).run("SELECT name FROM city ORDER BY name")
    assert err is None
    assert rows == [("A",), ("B",)]


def test_bad_sql_returns_error(db_path):
    rows, err = SqlSandbox(db_path).run("SELECT nope FROM city")
    assert rows is None
    assert "no such column" in err.lower()


def test_writes_are_blocked(db_path):
    rows, err = SqlSandbox(db_path).run("DELETE FROM city")
    assert rows is None
    assert err is not None  # read-only connection rejects writes
