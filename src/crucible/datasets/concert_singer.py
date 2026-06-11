"""Self-contained "concert_singer" benchmark: a real SQLite DB + gold SQL.

A faithful rebuild of the Spider ``concert_singer`` schema shape (stadium /
singer / concert / singer_in_concert) bundled directly in code so the live
server needs no external, license-bound data download. Every gold query below
executes against the database built by :func:`build_db`, so scores produced over
these items are real execution-match scores, not mocks.

Train and test share PATTERNS (JOIN, GROUP BY/HAVING, ORDER BY+LIMIT, subquery)
with DIFFERENT questions, so a fix the optimizer learns from a train failure can
genuinely generalize to the held-out test split.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile

from crucible.types import EvalItem

DB_ID = "concert_singer"

SCHEMA = """
CREATE TABLE stadium (
    stadium_id   INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    location     TEXT NOT NULL,
    capacity     INTEGER NOT NULL,
    highest      INTEGER NOT NULL,
    average      INTEGER NOT NULL
);
CREATE TABLE singer (
    singer_id    INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    country      TEXT NOT NULL,
    song_name    TEXT NOT NULL,
    age          INTEGER NOT NULL,
    is_male      INTEGER NOT NULL
);
CREATE TABLE concert (
    concert_id   INTEGER PRIMARY KEY,
    concert_name TEXT NOT NULL,
    theme        TEXT NOT NULL,
    stadium_id   INTEGER NOT NULL REFERENCES stadium(stadium_id),
    year         INTEGER NOT NULL
);
CREATE TABLE singer_in_concert (
    concert_id   INTEGER NOT NULL REFERENCES concert(concert_id),
    singer_id    INTEGER NOT NULL REFERENCES singer(singer_id)
);
"""

_STADIUMS = [
    (1, "Stark Arena", "Belgrade", 19500, 18100, 16200),
    (2, "Olympic Hall", "Munich", 12500, 11000, 9800),
    (3, "Wembley", "London", 90000, 86000, 74000),
    (4, "Madison Square", "New York", 20000, 19500, 17800),
    (5, "Tokyo Dome", "Tokyo", 55000, 52000, 47000),
]

_SINGERS = [
    (1, "Joe Strong", "United States", "Thunder Road", 41, 1),
    (2, "Mara Voss", "Germany", "Nightfall", 29, 0),
    (3, "Liang Wu", "China", "River Light", 34, 1),
    (4, "Aria Quinn", "United Kingdom", "Glass Houses", 52, 0),
    (5, "Tomas Reyes", "United States", "Open Sky", 27, 1),
    (6, "Nina Park", "United States", "Quiet Storm", 38, 0),
]

_CONCERTS = [
    (1, "Auto Awards", "Modern Rock", 1, 2014),
    (2, "Home Visit", "Acoustic Night", 2, 2014),
    (3, "Super Bootcamp", "Pop Explosion", 1, 2015),
    (4, "Week 1", "Indie Wave", 3, 2015),
    (5, "Week 2", "Stadium Anthems", 4, 2016),
    (6, "Year Finale", "Greatest Hits", 5, 2016),
]

_SINGER_IN_CONCERT = [
    (1, 1), (1, 2), (2, 3), (3, 1), (3, 5),
    (4, 4), (4, 6), (5, 1), (5, 2), (5, 5), (6, 3), (6, 4),
]

TRAIN: list[EvalItem] = [
    EvalItem("How many singers are there?",
             "SELECT count(*) FROM singer", DB_ID, "easy"),
    EvalItem("List the names of all singers from the United States.",
             "SELECT name FROM singer WHERE country='United States'", DB_ID, "easy"),
    # JOIN pattern
    EvalItem("Show each concert name along with the name of its stadium.",
             "SELECT concert.concert_name, stadium.name FROM concert "
             "JOIN stadium ON concert.stadium_id=stadium.stadium_id", DB_ID, "medium"),
    # GROUP BY pattern
    EvalItem("How many concerts were held in each year? Return the year and the count.",
             "SELECT year, count(*) FROM concert GROUP BY year", DB_ID, "medium"),
    # GROUP BY + HAVING pattern
    EvalItem("Which stadiums hosted more than one concert? Return the stadium name.",
             "SELECT stadium.name FROM concert JOIN stadium "
             "ON concert.stadium_id=stadium.stadium_id "
             "GROUP BY stadium.stadium_id HAVING count(*) > 1", DB_ID, "hard"),
    # ORDER BY + LIMIT pattern
    EvalItem("What is the name of the stadium with the largest capacity?",
             "SELECT name FROM stadium ORDER BY capacity DESC LIMIT 1", DB_ID, "hard"),
    # subquery pattern
    EvalItem("List the names of singers older than the average singer age.",
             "SELECT name FROM singer WHERE age > (SELECT avg(age) FROM singer)",
             DB_ID, "hard"),
    # JOIN across 3 tables pattern
    EvalItem("List the names of singers who performed in the concert named 'Auto Awards'.",
             "SELECT singer.name FROM singer "
             "JOIN singer_in_concert ON singer.singer_id=singer_in_concert.singer_id "
             "JOIN concert ON singer_in_concert.concert_id=concert.concert_id "
             "WHERE concert.concert_name='Auto Awards'", DB_ID, "hard"),
]

TEST: list[EvalItem] = [  # held-out: same patterns, different questions
    EvalItem("How many stadiums are there?",
             "SELECT count(*) FROM stadium", DB_ID, "easy"),
    # JOIN pattern (singer -> appearances)
    EvalItem("Show each singer name along with the name of a concert they performed in.",
             "SELECT singer.name, concert.concert_name FROM singer "
             "JOIN singer_in_concert ON singer.singer_id=singer_in_concert.singer_id "
             "JOIN concert ON singer_in_concert.concert_id=concert.concert_id", DB_ID, "medium"),
    # GROUP BY + HAVING pattern (singers per country)
    EvalItem("Which countries have more than one singer? Return the country.",
             "SELECT country FROM singer GROUP BY country HAVING count(*) > 1",
             DB_ID, "hard"),
    # ORDER BY + LIMIT pattern (oldest singer)
    EvalItem("What is the name of the oldest singer?",
             "SELECT name FROM singer ORDER BY age DESC LIMIT 1", DB_ID, "hard"),
    # subquery pattern (stadium capacity above average)
    EvalItem("List the names of stadiums whose capacity is above the average stadium capacity.",
             "SELECT name FROM stadium WHERE capacity > (SELECT avg(capacity) FROM stadium)",
             DB_ID, "hard"),
]


def build_db(target_dir: str | None = None) -> str:
    """Create and populate the bundled concert_singer SQLite DB; return its path."""
    directory = target_dir or tempfile.mkdtemp(prefix="crucible_concert_")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "concert_singer.sqlite")
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        con.executemany("INSERT INTO stadium VALUES (?,?,?,?,?,?)", _STADIUMS)
        con.executemany("INSERT INTO singer VALUES (?,?,?,?,?,?)", _SINGERS)
        con.executemany("INSERT INTO concert VALUES (?,?,?,?,?)", _CONCERTS)
        con.executemany("INSERT INTO singer_in_concert VALUES (?,?)", _SINGER_IN_CONCERT)
        con.commit()
    finally:
        con.close()
    return path
