"""S049 #79 (F021) — post-run dedup audit on the natural key.

The audit runs src/audit/sql/duplicate_natural_keys.sql — the same SQL
kept ready for Athena — on an in-memory sqlite table built from a run's
manifest.jsonl. Within one format a natural key must appear once.
"""
import json
import re
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
)


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
