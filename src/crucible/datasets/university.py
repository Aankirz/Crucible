"""Self-contained "university" benchmark: a real SQLite DB + gold SQL.

A student-records schema (department / student / course / enrollment) in the
Spider style, bundled directly in code so the live server needs no external,
license-bound data download. Every gold query below executes against the
database built by :func:`build_db`, so scores are real execution-match scores.

Train and test share PATTERNS (JOIN, GROUP BY/HAVING, ORDER BY+LIMIT, subquery)
with DIFFERENT questions, so a fix learned from a train failure can generalize
to the held-out test split.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile

from crucible.types import EvalItem

DB_ID = "university"

SCHEMA = """
CREATE TABLE department (
    dept_id   INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    building  TEXT NOT NULL
);
CREATE TABLE student (
    student_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    dept_id    INTEGER NOT NULL REFERENCES department(dept_id),
    gpa        REAL NOT NULL,
    year       INTEGER NOT NULL
);
CREATE TABLE course (
    course_id  INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    dept_id    INTEGER NOT NULL REFERENCES department(dept_id),
    credits    INTEGER NOT NULL
);
CREATE TABLE enrollment (
    student_id INTEGER NOT NULL REFERENCES student(student_id),
    course_id  INTEGER NOT NULL REFERENCES course(course_id),
    grade      REAL NOT NULL
);
"""

_DEPARTMENTS = [
    (1, "Computer Science", "Turing Hall"),
    (2, "Mathematics", "Euler Building"),
    (3, "Physics", "Newton Center"),
    (4, "History", "Herodotus Hall"),
]

_STUDENTS = [
    (1, "Alice Tan", 1, 3.8, 2),
    (2, "Bob Lee", 1, 3.1, 3),
    (3, "Carla Mendez", 2, 3.9, 1),
    (4, "Derek Osei", 2, 2.7, 4),
    (5, "Emi Sato", 3, 3.5, 2),
    (6, "Frank Webb", 3, 3.3, 3),
    (7, "Grace Hall", 1, 3.6, 1),
    (8, "Hassan Ali", 4, 2.9, 4),
]

_COURSES = [
    (1, "Intro to Programming", 1, 4),
    (2, "Algorithms", 1, 3),
    (3, "Linear Algebra", 2, 4),
    (4, "Calculus II", 2, 4),
    (5, "Classical Mechanics", 3, 3),
    (6, "World History", 4, 3),
]

_ENROLLMENTS = [
    (1, 1, 3.9), (1, 2, 3.7), (2, 1, 3.0), (2, 2, 2.8),
    (3, 3, 4.0), (3, 4, 3.8), (4, 3, 2.5), (5, 5, 3.6),
    (6, 5, 3.2), (7, 1, 3.5), (7, 2, 3.4), (8, 6, 2.9),
]

TRAIN: list[EvalItem] = [
    EvalItem("How many students are there?",
             "SELECT count(*) FROM student", DB_ID, "easy"),
    EvalItem("List the names of students whose GPA is above 3.5.",
             "SELECT name FROM student WHERE gpa > 3.5", DB_ID, "easy"),
    # JOIN pattern
    EvalItem("Show each student name along with the name of their department.",
             "SELECT student.name, department.name FROM student "
             "JOIN department ON student.dept_id=department.dept_id", DB_ID, "medium"),
    # GROUP BY pattern
    EvalItem("How many students are in each department? Return the department id and the count.",
             "SELECT dept_id, count(*) FROM student GROUP BY dept_id", DB_ID, "medium"),
    # GROUP BY + HAVING pattern
    EvalItem("Which departments have more than two students? Return the department name.",
             "SELECT department.name FROM student "
             "JOIN department ON student.dept_id=department.dept_id "
             "GROUP BY department.dept_id HAVING count(*) > 2", DB_ID, "hard"),
    # ORDER BY + LIMIT pattern
    EvalItem("What is the name of the student with the highest GPA?",
             "SELECT name FROM student ORDER BY gpa DESC LIMIT 1", DB_ID, "hard"),
    # subquery pattern
    EvalItem("List the names of students whose GPA is above the average student GPA.",
             "SELECT name FROM student WHERE gpa > (SELECT avg(gpa) FROM student)",
             DB_ID, "hard"),
    # JOIN across enrollment pattern
    EvalItem("List the titles of courses that student 'Alice Tan' is enrolled in.",
             "SELECT course.title FROM course "
             "JOIN enrollment ON course.course_id=enrollment.course_id "
             "JOIN student ON enrollment.student_id=student.student_id "
             "WHERE student.name='Alice Tan'", DB_ID, "hard"),
]

TEST: list[EvalItem] = [  # held-out: same patterns, different questions
    EvalItem("How many courses are there?",
             "SELECT count(*) FROM course", DB_ID, "easy"),
    # JOIN pattern (course -> department)
    EvalItem("Show each course title along with the name of its department.",
             "SELECT course.title, department.name FROM course "
             "JOIN department ON course.dept_id=department.dept_id", DB_ID, "medium"),
    # GROUP BY + HAVING pattern (courses per department)
    EvalItem("Which departments offer more than one course? Return the department id.",
             "SELECT dept_id FROM course GROUP BY dept_id HAVING count(*) > 1",
             DB_ID, "hard"),
    # ORDER BY + LIMIT pattern (most credits)
    EvalItem("What is the title of the course with the most credits? Return one title.",
             "SELECT title FROM course ORDER BY credits DESC LIMIT 1", DB_ID, "hard"),
    # subquery pattern (gpa below average)
    EvalItem("List the names of students whose GPA is below the average student GPA.",
             "SELECT name FROM student WHERE gpa < (SELECT avg(gpa) FROM student)",
             DB_ID, "hard"),
]


def build_db(target_dir: str | None = None) -> str:
    """Create and populate the bundled university SQLite DB; return its path."""
    directory = target_dir or tempfile.mkdtemp(prefix="crucible_university_")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "university.sqlite")
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        con.executemany("INSERT INTO department VALUES (?,?,?)", _DEPARTMENTS)
        con.executemany("INSERT INTO student VALUES (?,?,?,?,?)", _STUDENTS)
        con.executemany("INSERT INTO course VALUES (?,?,?,?)", _COURSES)
        con.executemany("INSERT INTO enrollment VALUES (?,?,?)", _ENROLLMENTS)
        con.commit()
    finally:
        con.close()
    return path
