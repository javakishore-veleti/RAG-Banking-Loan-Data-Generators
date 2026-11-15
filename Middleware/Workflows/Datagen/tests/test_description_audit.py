"""S050 #80 (F021) — the post-run audit also checks description overlap.

Metric is F013's wording-only word 5-gram Jaccard (uniqueness_check.py),
measured on the run's own txt documents. M003 limits: wording-only mean
<= 0.15 and same loan-type pairs with Jaccard > 0.5 <= 5%.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

DATAGEN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATAGEN / "src"))
sys.path.insert(0, str(DATAGEN))

import uniqueness_check  # noqa: E402
from audit import description_audit  # noqa: E402
from audit.dedup_audit import ManifestError, main  # noqa: E402
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


# ---------------------------------------------------------------- CLI: both checks

GEN = DATAGEN / "src" / "generator" / "generator.py"
AUDIT_PY = DATAGEN / "src" / "audit" / "dedup_audit.py"


def _generate(out, formats="txt,csv"):
    subprocess.run([sys.executable, str(GEN), "--count", "200", "--seed", "7",
                    "--formats", formats, "--out", str(out)],
                   check=True, capture_output=True)


def _near_identical_run(run, n=5):
    """A run whose txt descriptions differ only in numbers (same loan type)."""
    (run / "txt").mkdir(parents=True)
    rows = []
    for i in range(n):
        f = f"txt/loan_{i:07d}.txt"
        (run / f).write_text(TEMPLATE.format(n=i) + "\n", encoding="utf-8")
        rows.append({"doc_id": f"txt_{i:07d}", "format": "txt", "file": f,
                     "loan_id": f"LN{i}", "loan_type": "Home Loan",
                     "natural_hash": f"{i:064x}"})
    (run / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                        encoding="utf-8")
    return run


def test_generated_run_passes_overlap_limits(tmp_path, capsys):
    run = tmp_path / "run"
    _generate(run)
    assert main([str(run)]) == 0
    out = capsys.readouterr().out
    assert "200 descriptions, 19900 pairs" in out
    mean = float(re.search(r"wording-only mean=([0-9.]+)", out).group(1))
    pct = float(re.search(r"same-type >0.5=([0-9.]+)%", out).group(1))
    assert mean <= 0.15 and pct <= 5.0


def test_near_identical_run_fails(tmp_path, capsys):
    run = _near_identical_run(tmp_path / "run")
    assert main([str(run)]) == 1
    out = capsys.readouterr().out
    assert "0 duplicate natural key(s)" in out
    assert "OVERLAP" in out


def test_run_without_txt_exits_2(tmp_path, capsys):
    run = tmp_path / "run"
    _generate(run, formats="csv")
    assert main([str(run)]) == 2
    assert "no txt" in capsys.readouterr().err


def test_duplicates_and_overlap_both_reported(tmp_path, capsys):
    run = _near_identical_run(tmp_path / "run")
    manifest = run / "manifest.jsonl"
    first = manifest.read_text(encoding="utf-8").splitlines()[0]
    with open(manifest, "a", encoding="utf-8") as fh:
        fh.write(first + "\n")
    assert main([str(manifest)]) == 1
    out = capsys.readouterr().out
    assert "DUPLICATE" in out and "OVERLAP" in out


def test_script_reports_bad_txt_as_exit_2(tmp_path):
    run = _near_identical_run(tmp_path / "run")
    (run / "txt" / "loan_0000000.txt").unlink()
    res = subprocess.run([sys.executable, str(AUDIT_PY), str(run)],
                         capture_output=True, text=True)
    assert res.returncode == 2, res.stderr
    assert "not found" in res.stderr


def test_duplicates_reported_even_without_txt(tmp_path, capsys):
    run = tmp_path / "run"
    _generate(run, formats="csv")
    manifest = run / "manifest.jsonl"
    first = manifest.read_text(encoding="utf-8").splitlines()[0]
    with open(manifest, "a", encoding="utf-8") as fh:
        fh.write(first + "\n")
    assert main([str(run)]) == 2
    captured = capsys.readouterr()
    assert "1 duplicate natural key(s)" in captured.out
    assert "DUPLICATE format=csv" in captured.out
    assert "no txt" in captured.err
