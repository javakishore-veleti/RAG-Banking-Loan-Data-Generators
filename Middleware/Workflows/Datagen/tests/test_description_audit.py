"""S050 #80 (F021) — the post-run audit also checks description overlap.

Metric is F013's wording-only word 5-gram Jaccard (uniqueness_check.py),
measured on the run's own txt documents. M003 limits: wording-only mean
<= 0.15 and same loan-type pairs with Jaccard > 0.5 <= 5%.
"""
import sys
from pathlib import Path

import pytest

DATAGEN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATAGEN / "src"))
sys.path.insert(0, str(DATAGEN))

import uniqueness_check  # noqa: E402
from audit import description_audit  # noqa: E402
from audit.dedup_audit import ManifestError  # noqa: E402
from audit.description_audit import (  # noqa: E402
    limit_failures,
    load_descriptions,
    overlap_metrics,
)

TEMPLATE = ("Home Loan summary for customer {n} the interest rate is {n} percent "
            "and the tenure is {n} months with emi {n}")


def _doc(word):
    """12 words unique to `word`, so two docs share no 5-gram."""
    return " ".join(f"{word}{c}" for c in "abcdefghijkl")


# ---------------------------------------------------------------- metrics

def test_uses_the_f013_functions():
    assert description_audit.shingles is uniqueness_check.shingles
    assert description_audit.jaccard is uniqueness_check.jaccard


def test_near_identical_descriptions_fail():
    m = overlap_metrics([("Home Loan", TEMPLATE.format(n=i)) for i in range(5)])
    assert m["mean"] == 1.0
    assert m["same_type_high_pct"] == 100.0
    assert len(limit_failures(m)) == 2


def test_distinct_descriptions_pass():
    m = overlap_metrics([("Home Loan", _doc(w)) for w in ("ab", "cd", "ef", "gh", "ij")])
    assert m["mean"] == 0.0
    assert limit_failures(m) == []


def test_same_type_limit_checked_alone():
    docs = [("Home Loan", TEMPLATE.format(n=1)), ("Home Loan", TEMPLATE.format(n=2))]
    docs += [(f"Type {k}", _doc(w)) for k, w in enumerate(("ab", "cd", "ef", "gh", "ij", "kl", "mn", "op"))]
    m = overlap_metrics(docs)
    assert m["mean"] <= 0.15
    assert m["same_type_high_pct"] == 100.0
    fails = limit_failures(m)
    assert len(fails) == 1 and "same-type" in fails[0]


def test_limits_are_inclusive():
    assert limit_failures({"mean": 0.15, "same_type_high_pct": 5.0}) == []
    fails = limit_failures({"mean": 0.151, "same_type_high_pct": 5.0})
    assert len(fails) == 1 and "mean" in fails[0]
    fails = limit_failures({"mean": 0.15, "same_type_high_pct": 5.01})
    assert len(fails) == 1 and "same-type" in fails[0]


def test_one_description_has_no_pairs():
    m = overlap_metrics([("Home Loan", _doc("ab"))])
    assert m["pairs"] == 0 and m["mean"] == 0.0
    assert limit_failures(m) == []


def test_no_same_type_pairs():
    m = overlap_metrics([("A", _doc("ab")), ("B", _doc("cd")), ("C", _doc("ef"))])
    assert m["same_type_pairs"] == 0
    assert m["same_type_high_pct"] == 0.0


# ---------------------------------------------------------------- load_descriptions

def test_load_descriptions_reads_txt_rows_only(tmp_path):
    (tmp_path / "txt").mkdir()
    (tmp_path / "txt" / "a.txt").write_text(_doc("ab"), encoding="utf-8")
    rows = [{"format": "txt", "file": "txt/a.txt", "loan_type": "Home Loan"},
            {"format": "csv", "file": "csv/a.csv", "loan_type": "Home Loan"}]
    assert load_descriptions(rows, tmp_path) == [("Home Loan", _doc("ab"))]


@pytest.mark.parametrize("case, expected", [
    ("no_txt", "no txt"),
    ("missing_file", "not found"),
    ("bad_utf8", "UTF-8"),
    ("too_short", "too short"),
    ("no_file_field", "file"),
])
def test_load_descriptions_errors(tmp_path, case, expected):
    (tmp_path / "txt").mkdir()
    path = tmp_path / "txt" / "a.txt"
    row = {"format": "txt", "file": "txt/a.txt", "loan_type": "Home Loan"}
    if case == "no_txt":
        row["format"] = "csv"
    elif case == "missing_file":
        row["file"] = "txt/missing.txt"
    elif case == "bad_utf8":
        path.write_bytes(b"\xff\xfe broken")
    elif case == "too_short":
        path.write_text("only four words here", encoding="utf-8")
    elif case == "no_file_field":
        del row["file"]
    with pytest.raises(ManifestError, match=expected):
        load_descriptions([row], tmp_path)
