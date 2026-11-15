#!/usr/bin/env python3
"""F021 / S049 #79 — post-run dedup audit on a run's manifest.

Runs sql/duplicate_natural_keys.sql (the query kept ready for Athena)
on an in-memory sqlite table `manifest` built from manifest.jsonl.
Within one format, a natural_hash must appear once (F019 natural key).

Python stdlib only; no AWS calls.
"""
import json
import sqlite3
from pathlib import Path

SQL_PATH = Path(__file__).resolve().parent / "sql" / "duplicate_natural_keys.sql"
REQUIRED_FIELDS = ("format", "natural_hash")


class ManifestError(ValueError):
    """The manifest is missing, unreadable or has a malformed row."""


def load_manifest(path):
    """Rows of a manifest.jsonl. `path` is the file or a run directory
    holding manifest.jsonl. Blank lines are skipped."""
    path = Path(path)
    if path.is_dir():
        path = path / "manifest.jsonl"
    if not path.is_file():
        raise ManifestError(f"manifest not found: {path}")
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ManifestError(f"{path}: line {n}: not valid JSON ({exc.msg})") from None
            if not isinstance(row, dict):
                raise ManifestError(f"{path}: line {n}: not a JSON object")
            missing = [f for f in REQUIRED_FIELDS if not row.get(f)]
            if missing:
                raise ManifestError(f"{path}: line {n}: missing {', '.join(missing)}")
            rows.append(row)
    return rows


def find_duplicates(rows):
    """(format, natural_hash, duplicate_count) for every natural key that
    appears more than once within a format, from the SQL file."""
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE TABLE manifest (doc_id TEXT, format TEXT, loan_id TEXT, natural_hash TEXT)")
        con.executemany(
            "INSERT INTO manifest VALUES (?, ?, ?, ?)",
            [(r.get("doc_id"), r.get("format"), r.get("loan_id"), r.get("natural_hash")) for r in rows],
        )
        return [tuple(r) for r in con.execute(SQL_PATH.read_text(encoding="utf-8")).fetchall()]
    finally:
        con.close()
