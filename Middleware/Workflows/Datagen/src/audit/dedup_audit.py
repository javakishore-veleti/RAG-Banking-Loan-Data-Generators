#!/usr/bin/env python3
"""F021 / S049 #79 — post-run dedup audit on a run's manifest.

Runs sql/duplicate_natural_keys.sql (the query kept ready for Athena)
on an in-memory sqlite table `manifest` built from manifest.jsonl.
Within one format, a natural_hash must appear once (F019 natural key).

Usage:
  python3 src/audit/dedup_audit.py <manifest.jsonl | run dir>

Exit codes: 0 clean, 1 duplicates found, 2 bad input (missing or empty
manifest, malformed row). Python stdlib only; no AWS calls.
"""
import argparse
import json
import sqlite3
import sys
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
    try:
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, start=1):
                if line.strip():
                    rows.append(_parse_row(path, n, line))
    except UnicodeDecodeError as exc:
        raise ManifestError(f"{path}: not valid UTF-8 ({exc.reason} at byte {exc.start})") from None
    except OSError as exc:
        raise ManifestError(f"{path}: cannot read ({exc})") from None
    return rows


def _parse_row(path, n, line):
    """One manifest line as a dict; ManifestError naming the line if bad."""
    try:
        row = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path}: line {n}: not valid JSON ({exc.msg})") from None
    if not isinstance(row, dict):
        raise ManifestError(f"{path}: line {n}: not a JSON object")
    missing = [f for f in REQUIRED_FIELDS if not row.get(f)]
    if missing:
        raise ManifestError(f"{path}: line {n}: missing {', '.join(missing)}")
    # Bound columns must be strings (or absent for the ID columns), so
    # sqlite can bind them and 5 / "5" never collapse to one key.
    for field in REQUIRED_FIELDS + ("doc_id", "loan_id"):
        if field in row and row[field] is not None and not isinstance(row[field], str):
            raise ManifestError(f"{path}: line {n}: {field} must be a string")
    return row


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


def main(argv=None):
    ap = argparse.ArgumentParser(description="Post-run dedup audit on a run's manifest (F021).")
    ap.add_argument("manifest", help="manifest.jsonl, or the run directory that holds it")
    args = ap.parse_args(argv)
    try:
        rows = load_manifest(args.manifest)
        if not rows:
            raise ManifestError(f"empty manifest: {args.manifest}")
    except ManifestError as exc:
        print(f"Dedup audit: ERROR {exc}", file=sys.stderr)
        return 2
    dups = find_duplicates(rows)
    print(f"Dedup audit: {len(rows)} manifest rows, {len(dups)} duplicate natural key(s)")
    for fmt, h, count in dups:
        print(f"DUPLICATE format={fmt} natural_hash={h} count={count}")
    return 1 if dups else 0


if __name__ == "__main__":
    raise SystemExit(main())
