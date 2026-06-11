"""Self-contained "world" benchmark: a real SQLite DB + human-authored gold SQL.

This is a genuine text-to-SQL benchmark (the Spider ``world_1`` schema shape:
country / city / countrylanguage) bundled directly in code so the live server
needs no external, license-bound data download. Every gold query below executes
against the database built by :func:`build_world_db`, so scores produced over
these items are real execution-match scores, not mocks.

Train and test deliberately share PATTERNS (JOIN, GROUP BY/HAVING, ORDER BY+LIMIT,
correlated subquery) with DIFFERENT questions, so a fix the optimizer learns from
a train failure can genuinely generalize to the held-out test split.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile

from crucible.types import EvalItem

WORLD_SCHEMA = """
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

_WORLD_ROWS = """
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

WORLD_DB_ID = "world"

WORLD_TRAIN: list[EvalItem] = [
    EvalItem("How many countries are there?",
             "SELECT count(*) FROM country", WORLD_DB_ID, "easy"),
    EvalItem("List each city name along with the name of its country.",
             "SELECT city.name, country.name FROM city "
             "JOIN country ON city.country_code=country.code", WORLD_DB_ID, "medium"),
    EvalItem("How many cities does each country have? Return country code and the count.",
             "SELECT country_code, count(*) FROM city GROUP BY country_code",
             WORLD_DB_ID, "medium"),
    # HAVING pattern
    EvalItem("Which countries have more than one city? Return the country name.",
             "SELECT country.name FROM city JOIN country ON city.country_code=country.code "
             "GROUP BY country.code HAVING count(*) > 1", WORLD_DB_ID, "hard"),
    # ORDER BY + LIMIT pattern
    EvalItem("Which country has the most cities? Return its name.",
             "SELECT country.name FROM city JOIN country ON city.country_code=country.code "
             "GROUP BY country.code ORDER BY count(*) DESC LIMIT 1", WORLD_DB_ID, "hard"),
    # subquery pattern
    EvalItem("List the names of cities whose population is above the average city population.",
             "SELECT name FROM city WHERE population > (SELECT avg(population) FROM city)",
             WORLD_DB_ID, "hard"),
]

WORLD_TEST: list[EvalItem] = [  # held-out: same patterns, different questions
    EvalItem("List the names of countries in Asia.",
             "SELECT name FROM country WHERE continent='Asia'", WORLD_DB_ID, "easy"),
    # HAVING pattern (on languages)
    EvalItem("Which countries have more than one official language? Return the country code.",
             "SELECT country_code FROM countrylanguage WHERE is_official=1 "
             "GROUP BY country_code HAVING count(*) > 1", WORLD_DB_ID, "hard"),
    # ORDER BY + LIMIT pattern (on population)
    EvalItem("What is the name of the country with the largest population?",
             "SELECT name FROM country ORDER BY population DESC LIMIT 1", WORLD_DB_ID, "hard"),
    # subquery pattern (on countries)
    EvalItem("List the names of countries whose population is above the average country population.",
             "SELECT name FROM country WHERE population > (SELECT avg(population) FROM country)",
             WORLD_DB_ID, "hard"),
]


def build_world_db(target_dir: str | None = None) -> str:
    """Create and populate the bundled world SQLite DB; return its path.

    Args:
        target_dir: Directory to write ``world.sqlite`` into. A fresh temp dir is
            created when omitted.

    Returns:
        Absolute path to the populated SQLite database file.
    """
    directory = target_dir or tempfile.mkdtemp(prefix="crucible_world_")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "world.sqlite")
    con = sqlite3.connect(path)
    try:
        con.executescript(WORLD_SCHEMA + _WORLD_ROWS)
        con.commit()
    finally:
        con.close()
    return path
