# S049 #79 Dedup Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local post-run audit that runs a committed, Athena-ready
`GROUP BY format, natural_hash HAVING COUNT(*) > 1` query over a run's `manifest.jsonl`
and exits non-zero on duplicates.

**Architecture:** `src/audit/dedup_audit.py` loads JSONL rows into an in-memory sqlite3
table `manifest` and executes `src/audit/sql/duplicate_natural_keys.sql` read from disk.
CLI wraps it with exit codes 0/1/2. CI generates a small run and audits it.

**Tech Stack:** Python 3 stdlib only (`json`, `sqlite3`, `argparse`, `pathlib`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-S049-dedup-audit-design.md`

## Global Constraints

- No new dependencies; Python stdlib only. No AWS calls, no Glue/Athena infra.
- Do not modify `src/generator/`, `uniqueness_check.py` or `src/worker/` (Track A).
- SQL must be plain ANSI (no sqlite-only syntax) so Athena runs it unchanged over table `manifest`.
- Unique fields: `(format, natural_hash)`.
- Exit codes: 0 clean, 1 duplicates, 2 bad input.
- Test data only in pytest `tmp_path`; never committed.
- Commits `S049 #79: <imperative summary>`, author Kishore, no AI trailer.

## Review Focus

1. Empty manifest (0 rows) — must exit 2, not report clean (anti-goal in spec). Test in Task 2.
2. Path given as run directory instead of the `.jsonl` file — must find `manifest.jsonl` inside. Test in Task 1.
3. Trailing / blank lines in the JSONL (the worker joins with `\n`, generator ends with `\n`) — skipped, not errors. Test in Task 1.
4. Worker-style rows without `natural_hash` — exit 2 naming the line, not a silent pass. Test in Task 1 (loader) and Task 2 (CLI).
5. Extra columns (question/answer text containing quotes, unicode) — must not break inserts; only the needed columns are loaded, via parameter binding. Covered by the generated-run test in Task 2.

---

### Task 1: SQL file, loader and `find_duplicates`

**Files:**
- Create: `Middleware/Workflows/Datagen/src/audit/__init__.py`
- Create: `Middleware/Workflows/Datagen/src/audit/sql/duplicate_natural_keys.sql`
- Create: `Middleware/Workflows/Datagen/src/audit/dedup_audit.py`
- Test: `Middleware/Workflows/Datagen/tests/test_dedup_audit.py`

**Interfaces:**
- Produces:
  - `SQL_PATH: pathlib.Path` — the `.sql` file.
  - `class ManifestError(ValueError)`.
  - `load_manifest(path: str | Path) -> list[dict]` — file or directory containing `manifest.jsonl`; raises `ManifestError` (message includes `line <n>`) on bad JSON or missing `format`/`natural_hash`, and on a missing file.
  - `find_duplicates(rows: list[dict]) -> list[tuple[str, str, int]]` — `(format, natural_hash, duplicate_count)`, ordered by format, natural_hash.

- [ ] **Step 1: Write failing tests** (helper `_row(fmt, h, doc_id="txt_0000000", loan_id="LN1")` builds a minimal row; `_write(tmp_path, rows)` writes `manifest.jsonl`):
  - `test_sql_file_is_the_athena_query`: text of `SQL_PATH` (lowercased, whitespace-collapsed) contains `from manifest`, `group by format, natural_hash`, `having count(*) > 1`.
  - `test_find_duplicates_runs_the_sql_file`: monkeypatch `dedup_audit.SQL_PATH` to a tmp file with `SELECT 'x', 'y', 9` → result `[("x", "y", 9)]` (proves the file is read, not a copy).
  - `test_clean_rows_have_no_duplicates`: 3 distinct hashes → `[]`.
  - `test_injected_duplicate_is_reported`: rows `a,b,a` in `txt` → `[("txt", "a", 2)]`.
  - `test_same_key_different_ids_is_reported`: two `txt` rows hash `a`, doc_ids `txt_0000000`/`txt_0000001`, loan_ids `LN1`/`LN2` → `[("txt","a",2)]`.
  - `test_same_key_other_format_is_not_reported`: `("txt","a")`, `("csv","a")` → `[]`.
  - `test_load_manifest_accepts_run_dir_and_skips_blank_lines`: write 2 rows plus `"\n\n"`; `load_manifest(tmp_path)` and `load_manifest(tmp_path/"manifest.jsonl")` both return 2 rows.
  - `test_load_manifest_bad_json_names_line`: line 2 is `{not json` → `ManifestError` matching `line 2`.
  - `test_load_manifest_missing_natural_hash_names_line`: row without `natural_hash` on line 1 → `ManifestError` matching `line 1` and `natural_hash`.
  - `test_load_manifest_missing_file`: nonexistent path → `ManifestError`.
- [ ] **Step 2: Run** `$V -m pytest Middleware/Workflows/Datagen/tests/test_dedup_audit.py -q` → FAIL (ModuleNotFoundError `audit`).
- [ ] **Step 3: Implement.** SQL file: header `--` comments (purpose, Athena usage: Glue table `manifest` over `manifests/<run_id>/` JSONL, needs columns `format`, `natural_hash`), then
  `SELECT format, natural_hash, COUNT(*) AS duplicate_count FROM manifest GROUP BY format, natural_hash HAVING COUNT(*) > 1 ORDER BY format, natural_hash`.
  `find_duplicates`: `sqlite3.connect(":memory:")`, `CREATE TABLE manifest (doc_id TEXT, format TEXT, loan_id TEXT, natural_hash TEXT)`, `executemany` with `?` binding, `execute(SQL_PATH.read_text())`, return `[tuple(r) for r in fetchall()]`. Read `SQL_PATH` through the module global at call time (so the monkeypatch test works). `sqlite3.execute` rejects multiple statements, so the file holds exactly one statement (trailing `;` is allowed).
- [ ] **Step 4: Run** same command → all PASS; full Datagen suite count = 31 + 10.
- [ ] **Step 5: Commit** `S049 #79: add natural-key duplicate SQL and audit loader` (stage the four files by name).

### Task 2: CLI with exit codes, proven on a generated run

**Files:**
- Modify: `Middleware/Workflows/Datagen/src/audit/dedup_audit.py` (add `main`)
- Test: `Middleware/Workflows/Datagen/tests/test_dedup_audit.py`

**Interfaces:**
- Consumes: `load_manifest`, `find_duplicates`, `ManifestError` (Task 1).
- Produces: `main(argv: list[str] | None = None) -> int`; script entry `raise SystemExit(main())`. Output first line `Dedup audit: <N> manifest rows, <D> duplicate natural key(s)`; each duplicate line `DUPLICATE format=<f> natural_hash=<h> count=<n>`; errors to stderr as `Dedup audit: ERROR <message>`.

- [ ] **Step 1: Write failing tests.** Fixture `generated_run(tmp_path)` runs the generator as a subprocess: `[sys.executable, GEN, "--count", "200", "--seed", "7", "--formats", "txt,csv", "--out", str(tmp_path/"run")]`, `check=True`.
  - `test_generated_run_audits_clean`: `main([str(run)]) == 0`; captured stdout contains `400 manifest rows, 0 duplicate`.
  - `test_cli_injected_duplicate_exits_1`: append line 1 of the generated manifest again → `main == 1`; stdout contains `DUPLICATE format=txt natural_hash=<that hash> count=2`.
  - `test_replayed_run_is_reported`: run the generator a second time into the same `--out` → `main == 1`; stdout contains `400 duplicate natural key(s)`.
  - `test_cli_bad_input_exits_2` parametrized: missing path; empty manifest file; row without `natural_hash` → each `main == 2`, stderr contains `ERROR`.
  - `test_cli_script_runs_standalone`: subprocess `[sys.executable, AUDIT_PY, str(run)]` returncode 0 (proves the file runs as a script, not only as an import).
- [ ] **Step 2: Run** → FAIL (`main` missing).
- [ ] **Step 3: Implement `main`** with `argparse` (one positional `manifest`); empty row list → `ManifestError("empty manifest: <path>")`. Script mode needs no `sys.path` tweak since it imports only stdlib.
- [ ] **Step 4: Run** → PASS; Datagen suite = 31 + 10 + 7.
- [ ] **Step 5: Commit** `S049 #79: add dedup audit CLI with exit codes`.

### Task 3: CI runs the audit on a generated run

**Files:**
- Modify: `.github/workflows/ci.yml` (after the `uniqueness_check.py` step)

- [ ] **Step 1:** Add step:
  `- run: python3 Middleware/Workflows/Datagen/src/generator/generator.py --count 200 --seed 7 --formats txt,csv --out "$RUNNER_TEMP/audit-run" && python3 Middleware/Workflows/Datagen/src/audit/dedup_audit.py "$RUNNER_TEMP/audit-run"`
  and add `Middleware/Workflows/Datagen/src/audit/dedup_audit.py` to the existing `py_compile` line.
- [ ] **Step 2: Verify locally:** same commands with `RUNNER_TEMP=runtime_data/tmp/s049-ci` → exit 0; `python3 -c "import yaml"` is not available, so check the YAML by eye in the diff (2-space indent, list item under `steps`).
- [ ] **Step 3: Commit** `S049 #79: run dedup audit in CI`. CI on the PR is the real check.

## Self-review

Spec coverage: A1 → T1 `test_sql_file_is_the_athena_query`; A2 → T1 `test_find_duplicates_runs_the_sql_file`; A3 → T2 `test_generated_run_audits_clean`; A4 → T1 + T2 injected tests; A5 → T1 `test_same_key_different_ids_is_reported`; A6 → T1 `test_same_key_other_format_is_not_reported`; A7 → T2 `test_replayed_run_is_reported`; A8 → T1 loader tests + T2 `test_cli_bad_input_exits_2`; A9 → suite counts in T1/T2 step 4; A10 → T3. No gaps.

## Review findings (step 9)

_(filled in at step 9)_
