"""Read-only SQLite execution with a statement timeout.

The read-only connection is the safety boundary: generated SQL can SELECT but never
mutate the database. A timer interrupts runaway queries.
"""
import sqlite3
import threading


class SqlSandbox:
    def __init__(self, db_path: str, timeout_s: float = 5.0):
        self._db_path = db_path
        self._timeout_s = timeout_s

    def run(self, sql: str):
        """Execute SQL read-only. Returns (rows, error); rows is None on error/timeout."""
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        except sqlite3.Error as e:
            return None, str(e)
        timer = threading.Timer(self._timeout_s, conn.interrupt)
        try:
            timer.start()
            rows = conn.execute(sql).fetchall()
            return rows, None
        except sqlite3.Error as e:
            return None, str(e)
        finally:
            timer.cancel()
            conn.close()
