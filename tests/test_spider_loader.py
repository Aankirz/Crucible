import json

from crucible.datasets.spider_loader import load_spider_dev


def test_loads_and_filters_by_db(tmp_path):
    dev = [
        {"db_id": "world_1", "question": "How many cities?", "query": "SELECT count(*) FROM city"},
        {"db_id": "other", "question": "x", "query": "SELECT 1"},
    ]
    p = tmp_path / "dev.json"
    p.write_text(json.dumps(dev))
    items = load_spider_dev(str(p), db_id="world_1")
    assert len(items) == 1
    assert items[0].db_id == "world_1"
    assert items[0].question == "How many cities?"
    assert items[0].difficulty in ("easy", "medium", "hard", "extra")
