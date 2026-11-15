# S049 #79 — Post-run dedup audit on the natural key (design)

**Story:** #79 S049 — Athena/Glue audit: `GROUP BY <unique fields> HAVING COUNT(*) > 1`
must return 0 rows. **Feature:** #78 F021 — Post-run dedup audit. **Epic:** #6 E006.
**Date:** 2026-11-15. **Size:** small change (short design).

## Intent

F019 stops duplicates at write time (atomic claim of `natural_hash`). F021 proves it after
the fact: a run is audited and any natural key that appears more than once is reported.
DESIGN.md §6 names the audit: `GROUP BY <unique fields> HAVING COUNT(*) > 1` in
Athena/Glue. Milestone decision (Milestone_003.md §5, 2026-11-15): M003 closes on **local
proof** — the audit runs locally on a generated run's manifest, and the same SQL is kept in
the repo, ready for Athena in M004/M005.

## What exists today

- Every manifest row (`manifest.jsonl`, written by `src/generator/generator.py`) has
  `doc_id`, `format`, `file`, `loan_id`, `loan_type`, `channel`, `question`, `answer`,
  `policy_version`, `natural_hash`. One row per record **per format**.
- `natural_hash` is SHA256 of the normalised F019 natural key
  `(customer, loan_type, amount, rate, tenure, start_date)` (`src/dedup/natural_hash.py`).
  The raw key fields are not in the manifest; the hash stands for them.
- The generator opens the manifest in append mode, so re-running into the same output
  directory duplicates every row — a real replay case the audit must catch.

## The unique fields

Within one format, a natural key must appear once. The audit's unique fields are therefore
`(format, natural_hash)`. Grouping by `natural_hash` alone would flag every record that was
rendered in more than one format, which is by design.

## Approaches

1. **SQL file + stdlib `sqlite3` in-memory (chosen).** Load the manifest rows into an
   in-memory table `manifest`, run the committed `.sql` file verbatim. The SQL is plain
   ANSI (`SELECT … GROUP BY … HAVING COUNT(*) > 1 ORDER BY …`), which Athena (Trino) runs
   unchanged over a Glue table named `manifest`. One query text, two engines. No new
   dependency.
2. **Pure Python `collections.Counter`.** Simplest, but the "Athena-ready" SQL would be a
   second, untested copy that can drift. Rejected.
3. **Glue table + Athena query in CloudFormation now.** Real AWS proof, but the milestone
   decided local proof, and AWS infra/calls are out of scope for M003. Rejected (M004/M005).

Decision (delegated by Kishore to the developer for this run): approach 1 — the only one
where the SQL that will run in Athena is the SQL the tests run.

## Design

- `Middleware/Workflows/Datagen/src/audit/__init__.py` (empty package marker).
- `Middleware/Workflows/Datagen/src/audit/sql/duplicate_natural_keys.sql` — the audit query
  over table `manifest`: `SELECT format, natural_hash, COUNT(*) AS duplicate_count FROM
  manifest GROUP BY format, natural_hash HAVING COUNT(*) > 1 ORDER BY format, natural_hash`.
  A header comment says how to run it in Athena (Glue table `manifest` over the run's
  `manifests/<run_id>/` JSONL prefix).
- `Middleware/Workflows/Datagen/src/audit/dedup_audit.py`:
  - `load_manifest(path)` — reads JSONL; `path` may be a `manifest.jsonl` file or a run
    directory containing one. Blank lines are skipped. A line that is not JSON, or a row
    without `format` or `natural_hash`, raises `ManifestError` naming the line number.
  - `find_duplicates(rows)` — creates in-memory sqlite table `manifest(doc_id, format,
    loan_id, natural_hash)`, inserts the rows, runs the SQL file, returns a list of
    `(format, natural_hash, duplicate_count)` tuples.
  - `main(argv)` — CLI `python3 src/audit/dedup_audit.py <manifest-or-run-dir>`. Prints
    `Dedup audit: <N> manifest rows, <D> duplicate natural key(s)` and one line per
    duplicate. Exit 0 when clean, 1 when duplicates are found, 2 on bad input (missing
    file, malformed row).
- CI: the existing `pytest Middleware/Workflows/Datagen/tests/` step runs the audit tests,
  which generate a 200-record run and audit it, so every PR proves a clean run audits clean.
  (A dedicated workflow step was planned but cannot be pushed: the push token lacks the
  GitHub `workflow` scope. The one-line step is in the plan for Kishore to add if wanted.)

Non-goals: Glue/Athena infrastructure, AWS calls, description overlap (that is S050 #80),
changes to the generator or `uniqueness_check.py`. Anti-goal: an audit that passes because
it reads nothing — an empty manifest is an error (exit 2), not a clean pass.

Found during design (follow-up, not built here): the Batch worker's S3 shard manifest rows
(`src/worker/batch_worker.py`, `manifests/<run_id>/<shard_id>.jsonl`) do not carry
`natural_hash`, so the Athena run of this SQL needs that column added to the worker row
first. The worker belongs to Track A (S047/S048) in this milestone, so this story does not
touch it; the audit reports such rows as bad input (exit 2) instead of passing silently.
Policy manifests (`record_kind: policy`, F018) have no natural key and are out of scope.

Left to the builder: exact print format, test fixture helpers.

## Acceptance

- [ ] A1 — `src/audit/sql/duplicate_natural_keys.sql` exists and is
  `GROUP BY format, natural_hash HAVING COUNT(*) > 1` over table `manifest`, plain SQL
  with no sqlite-only syntax (ready for Athena).
- [ ] A2 — `dedup_audit.find_duplicates` runs that file's SQL text (read from disk, not a
  copy) on an in-memory sqlite table built from the manifest rows.
- [ ] A3 — A clean generated run (generator `--count 200 --seed 7 --formats txt,csv`, into a temp
  dir; two formats so the per-format grouping is exercised, and the run takes < 1 s)
  audits to 0 rows; the CLI exits 0.
- [ ] A4 — A manifest with one injected duplicate row returns exactly that
  `(format, natural_hash)` with `duplicate_count` 2; the CLI exits 1 and prints it.
- [ ] A5 — Two rows with the same natural key but different `doc_id`/`loan_id` are reported
  (duplicates "even with different PKs", DESIGN.md §6).
- [ ] A6 — The same natural key in two different formats is NOT reported.
- [ ] A7 — Re-running the generator into the same output directory (replay) is reported as
  duplicates.
- [ ] A8 — Malformed input (bad JSON, missing `natural_hash`, missing file, empty manifest)
  exits 2 with a message naming the problem.
- [ ] A9 — No new dependencies; both test suites pass and the new tests are collected
  (Datagen count goes up).
- [ ] A10 — CI runs the audit on a freshly generated run (through the existing Datagen
  pytest step: `test_generated_run_audits_clean`, `test_cli_script_runs_standalone`).
