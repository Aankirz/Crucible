"""Load Spider/BIRD dev records (human gold SQL) into EvalItems."""
import json
from pathlib import Path

from crucible.types import EvalItem
from crucible.datasets.hardness import classify_hardness


def load_spider_dev(path: str, db_id: str | None = None) -> list[EvalItem]:
    records = json.loads(Path(path).read_text())
    items = []
    for r in records:
        if db_id is not None and r["db_id"] != db_id:
            continue
        items.append(
            EvalItem(
                question=r["question"],
                gold_sql=r["query"],
                db_id=r["db_id"],
                difficulty=classify_hardness(r["query"]),
            )
        )
    return items
