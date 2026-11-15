"""S049 #79 (F021) — post-run dedup audit on the natural key.

The audit runs src/audit/sql/duplicate_natural_keys.sql — the same SQL
kept ready for Athena — on an in-memory sqlite table built from a run's
manifest.jsonl. Within one format a natural key must appear once.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audit import dedup_audit  # noqa: E402
from audit.dedup_audit import (  # noqa: E402
    SQL_PATH,
    ManifestError,
    find_duplicates,
    load_manifest,
    main,
)

DATAGEN = Path(__file__).resolve().parents[1]
GEN = DATAGEN / "src" / "generator" / "generator.py"
AUDIT_PY = DATAGEN / "src" / "audit" / "dedup_audit.py"


def _row(fmt, h, doc_id="txt_0000000", loan_id="LN1"):
    return {"doc_id": doc_id, "format": fmt, "loan_id": loan_id, "natural_hash": h}


def _write(tmp_path, rows, tail=""):
    path = tmp_path / "manifest.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows) + tail, encoding="utf-8")
    return path


# ---------------------------------------------------------------- SQL + find_duplicates

def test_sql_file_is_the_athena_query():
    sql = re.sub(r"\s+", " ", SQL_PATH.read_text(encoding="utf-8").lower())
    assert "from manifest" in sql
    assert "group by format, natural_hash" in sql
    assert "having count(*) > 1" in sql


def test_find_duplicates_runs_the_sql_file(tmp_path, monkeypatch):
    fake = tmp_path / "fake.sql"
    fake.write_text("SELECT 'x', 'y', 9", encoding="utf-8")
    monkeypatch.setattr(dedup_audit, "SQL_PATH", fake)
    assert find_duplicates([_row("txt", "a")]) == [("x", "y", 9)]


def test_clean_rows_have_no_duplicates():
    rows = [_row("txt", "a"), _row("txt", "b"), _row("txt", "c")]
    assert find_duplicates(rows) == []


def test_injected_duplicate_is_reported():
    rows = [_row("txt", "a"), _row("txt", "b"), _row("txt", "a")]
    assert find_duplicates(rows) == [("txt", "a", 2)]


def test_same_key_different_ids_is_reported():
    rows = [_row("txt", "a", doc_id="txt_0000000", loan_id="LN1"),
            _row("txt", "a", doc_id="txt_0000001", loan_id="LN2")]
    assert find_duplicates(rows) == [("txt", "a", 2)]


def test_same_key_other_format_is_not_reported():
    assert find_duplicates([_row("txt", "a"), _row("csv", "a")]) == []


# ---------------------------------------------------------------- load_manifest

def test_load_manifest_accepts_run_dir_and_skips_blank_lines(tmp_path):
    _write(tmp_path, [_row("txt", "a"), _row("txt", "b")], tail="\n\n")
    assert len(load_manifest(tmp_path)) == 2
    assert len(load_manifest(tmp_path / "manifest.jsonl")) == 2


def test_load_manifest_bad_json_names_line(tmp_path):
    _write(tmp_path, [_row("txt", "a")], tail="{not json\n")
    with pytest.raises(ManifestError, match="line 2"):
        load_manifest(tmp_path)


def test_load_manifest_missing_natural_hash_names_line(tmp_path):
    _write(tmp_path, [{"doc_id": "txt_0000000", "format": "txt"}])
    with pytest.raises(ManifestError, match=r"line 1.*natural_hash"):
        load_manifest(tmp_path)


def test_load_manifest_missing_file(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "nope")


# ---------------------------------------------------------------- CLI on a generated run

def _generate(out):
    subprocess.run([sys.executable, str(GEN), "--count", "200", "--seed", "7",
                    "--formats", "txt,csv", "--out", str(out)],
                   check=True, capture_output=True)


@pytest.fixture
def generated_run(tmp_path):
    run = tmp_path / "run"
    _generate(run)
    return run


def test_generated_run_audits_clean(generated_run, capsys):
    assert main([str(generated_run)]) == 0
    assert "400 manifest rows, 0 duplicate" in capsys.readouterr().out


def test_cli_injected_duplicate_exits_1(generated_run, capsys):
    manifest = generated_run / "manifest.jsonl"
    first = manifest.read_text(encoding="utf-8").splitlines()[0]
    with open(manifest, "a", encoding="utf-8") as fh:
        fh.write(first + "\n")
    h = json.loads(first)["natural_hash"]
    assert main([str(generated_run)]) == 1
    assert f"DUPLICATE format=txt natural_hash={h} count=2" in capsys.readouterr().out


def test_replayed_run_is_reported(generated_run, capsys):
    _generate(generated_run)  # same --out again: the manifest is appended
    assert main([str(generated_run)]) == 1
    assert "400 duplicate natural key(s)" in capsys.readouterr().out


@pytest.mark.parametrize("case, expected", [
    ("missing", ["not found"]),
    ("empty", ["empty manifest"]),
    ("no_hash", ["line 1", "natural_hash"]),
    ("list_hash", ["line 1", "natural_hash", "string"]),
    ("dict_doc_id", ["line 1", "doc_id", "string"]),
    ("bad_utf8", ["UTF-8"]),
])
def test_cli_bad_input_exits_2(tmp_path, capsys, case, expected):
    path = tmp_path / "manifest.jsonl"
    if case == "empty":
        path.write_text("", encoding="utf-8")
    elif case == "no_hash":
        _write(tmp_path, [{"doc_id": "pdf_0000000", "format": "pdf"}])
    elif case == "list_hash":
        _write(tmp_path, [{"format": "txt", "natural_hash": ["a"]}])
    elif case == "dict_doc_id":
        _write(tmp_path, [{"format": "txt", "natural_hash": "a", "doc_id": {"x": 1}}])
    elif case == "bad_utf8":
        path.write_bytes(b'{"format": "txt", "natural_hash": "\xff"}\n')
    target = tmp_path / "nope" if case == "missing" else tmp_path
    assert main([str(target)]) == 2
    err = capsys.readouterr().err
    assert "ERROR" in err
    for text in expected:
        assert text in err


def test_cli_unreadable_file_exits_2(tmp_path, capsys, monkeypatch):
    _write(tmp_path, [_row("txt", "a")])

    def _deny(*a, **k):
        raise PermissionError("permission denied")
    monkeypatch.setattr("builtins.open", _deny)
    assert main([str(tmp_path)]) == 2
    assert "permission denied" in capsys.readouterr().err


def test_cli_script_runs_standalone(generated_run):
    res = subprocess.run([sys.executable, str(AUDIT_PY), str(generated_run)],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
