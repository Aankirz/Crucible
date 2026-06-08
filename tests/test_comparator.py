from crucible.comparator import compare_results, gold_requires_order


def test_identical_unordered_rows_match():
    assert compare_results([(1, "a"), (2, "b")], [(2, "b"), (1, "a")], order_matters=False).is_match


def test_duplicates_are_significant():
    # multiset: counts matter (COUNT vs COUNT DISTINCT bug must surface)
    assert not compare_results([(1,), (1,)], [(1,)], order_matters=False).is_match


def test_order_sensitive_when_required():
    assert not compare_results([(1,), (2,)], [(2,), (1,)], order_matters=True).is_match


def test_column_count_mismatch_fails():
    assert not compare_results([(1, "a")], [(1,)], order_matters=False).is_match


def test_numeric_tolerance_int_vs_float():
    assert compare_results([(5,)], [(5.0,)], order_matters=False).is_match


def test_string_whitespace_normalized():
    assert compare_results([("usa",)], [("usa ",)], order_matters=False).is_match


def test_both_empty_match():
    assert compare_results([], [], order_matters=False).is_match


def test_one_empty_one_not_fails():
    assert not compare_results([], [(1,)], order_matters=False).is_match


def test_null_result_fails():
    assert not compare_results(None, [(1,)], order_matters=False).is_match


def test_gold_requires_order_detects_order_by():
    assert gold_requires_order("SELECT name FROM t ORDER BY age")
    assert not gold_requires_order("SELECT count(*) FROM t")
