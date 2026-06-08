from crucible.datasets.hardness import classify_hardness


def test_simple_select_is_easy():
    assert classify_hardness("SELECT name FROM city") == "easy"


def test_single_join_is_medium():
    assert classify_hardness(
        "SELECT c.name FROM city c JOIN country o ON c.cid=o.id WHERE o.pop>100"
    ) == "medium"


def test_group_having_is_hard():
    assert classify_hardness(
        "SELECT cid, count(*) FROM city GROUP BY cid HAVING count(*)>2 ORDER BY cid"
    ) in ("hard", "extra")


def test_nested_is_extra():
    assert classify_hardness(
        "SELECT name FROM city WHERE pop > (SELECT avg(pop) FROM city) "
        "AND cid IN (SELECT id FROM country WHERE continent='Asia') GROUP BY name"
    ) == "extra"
