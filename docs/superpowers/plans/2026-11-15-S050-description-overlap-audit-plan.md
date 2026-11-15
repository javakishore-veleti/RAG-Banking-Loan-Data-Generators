# S050 #80 Description Overlap Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The post-run audit also measures F013 wording-only description overlap on the run's
txt documents and fails above the M003 limits (mean ≤ 0.15, same-type > 0.5 ≤ 5%).

**Architecture:** New `src/audit/description_audit.py` (load txt descriptions, compute
metrics with `uniqueness_check.shingles`/`jaccard`, compare to the limits), wired into
`dedup_audit.main` next to the S049 duplicate-key check.

**Tech Stack:** Python 3 stdlib, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-S050-description-overlap-audit-design.md`

## Global Constraints

- No new dependencies; no AWS calls. Do not modify `uniqueness_check.py`, `src/generator/`, `src/worker/`.
- Metric = F013 wording-only: `shingles(re.sub(r"\d+", "#", text), keep_numbers=False)` and `jaccard` imported from `uniqueness_check.py`.
- Limits: `WORDING_MEAN_MAX = 0.15`, `SAME_TYPE_HIGH = 0.5`, `SAME_TYPE_PCT_MAX = 5.0`; inclusive (at the limit passes).
- Exit codes: 0 clean, 1 duplicates or overlap failure, 2 bad input.
- Test data only in pytest `tmp_path`. Commits `S050 #80: <summary>`, author Kishore, no AI trailer.

## Review Focus

1. A txt document that is empty (or has fewer than 5 words) gives an empty shingle set and Jaccard 0 — it would silently lower the mean. Expected: `ManifestError` (exit 2). Test in Task 1.
2. Non-UTF-8 or missing txt file — `ManifestError`, not a traceback. Test in Task 1.
3. A run with exactly one txt description — 0 pairs, passes, no division by zero. Test in Task 1.
4. A run with no same-type pairs (all loan types distinct) — `same_type_high_pct` 0.0, no division by zero. Test in Task 1.
5. Duplicate rows plus overlap failure together — both reported, exit 1. Test in Task 2.

---

### Task 1: `description_audit` metrics and limits

**Files:**
- Create: `Middleware/Workflows/Datagen/src/audit/description_audit.py`
- Test: `Middleware/Workflows/Datagen/tests/test_description_audit.py`

**Interfaces:**
- Consumes: `audit.dedup_audit.ManifestError`; `uniqueness_check.shingles`, `uniqueness_check.jaccard`.
- Produces:
  - constants `WORDING_MEAN_MAX`, `SAME_TYPE_HIGH`, `SAME_TYPE_PCT_MAX` (values above).
  - `load_descriptions(rows: list[dict], base_dir: Path) -> list[tuple[str, str]]` — `(loan_type, text)` for rows with `format == "txt"`, reading `base_dir / row["file"]`.
  - `overlap_metrics(descriptions: list[tuple[str, str]]) -> dict` — keys `descriptions`, `pairs`, `mean`, `same_type_pairs`, `same_type_high_pct` (percent, 0–100).
  - `limit_failures(metrics: dict) -> list[str]`.

- [ ] **Step 1: Write failing tests.** Helper `_doc(word)` returns a 12-word text built from `word` (e.g. `f"{word}a {word}b ... {word}l"`) so distinct words give disjoint shingles; `TEMPLATE = "Home Loan summary for customer {n} the interest rate is {n} percent and the tenure is {n} months with emi {n}"`.
  - `test_uses_the_f013_functions`: `description_audit.shingles is uniqueness_check.shingles` and the same for `jaccard`.
  - `test_near_identical_descriptions_fail`: 5 × `("Home Loan", TEMPLATE.format(n=i))` → `mean == 1.0`, `same_type_high_pct == 100.0`, `limit_failures` has 2 entries.
  - `test_distinct_descriptions_pass`: 5 `_doc` texts with distinct words, all "Home Loan" → `mean == 0.0`, `limit_failures == []`.
  - `test_same_type_limit_checked_alone`: two identical "Home Loan" `TEMPLATE` texts + 8 `_doc` texts of 8 distinct other types → `mean <= 0.15`, `same_type_high_pct == 100.0`, exactly 1 failure containing `same-type`.
  - `test_limits_are_inclusive`: `limit_failures({"mean": 0.15, "same_type_high_pct": 5.0, ...})` is `[]`; `0.151` → 1 failure containing `mean`; `5.01` → 1 failure containing `same-type`.
  - `test_one_description_has_no_pairs`: 1 doc → `pairs == 0`, `mean == 0.0`, no failures.
  - `test_no_same_type_pairs`: 3 docs of 3 types → `same_type_pairs == 0`, `same_type_high_pct == 0.0`.
  - `test_load_descriptions_reads_txt_rows_only` (tmp_path): write `txt/a.txt`; rows `[{"format":"txt","file":"txt/a.txt","loan_type":"Home Loan"}, {"format":"csv","file":"csv/a.csv","loan_type":"Home Loan"}]` → `[("Home Loan", <text>)]`.
  - `test_load_descriptions_errors` parametrized → `ManifestError` with substring: no txt rows → `no txt`; missing file → `not found`; non-UTF-8 bytes → `UTF-8`; text with < 5 words → `too short`; row without `file` → `file`.
- [ ] **Step 2: Run** `$V -m pytest Middleware/Workflows/Datagen/tests/test_description_audit.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement.** Import: add `Path(__file__).resolve().parents[2]` (Datagen root) to `sys.path`, then `from uniqueness_check import jaccard, shingles`. Wording-only shingles computed once per description. Pairs via `itertools.combinations`. Mean of all pair Jaccards; same-type percent = `100 * count(j > SAME_TYPE_HIGH) / same_type_pairs`. Failure messages: `wording-only mean <m:.3f> > 0.15` and `same-type pairs >0.5 <p:.2f>% > 5%`.
- [ ] **Step 4: Run** → PASS; Datagen suite = 59 + 13 (count of new test cases).
- [ ] **Step 5: Commit** `S050 #80: add description overlap metrics and limits`.

### Task 2: audit CLI runs both checks

**Files:**
- Modify: `Middleware/Workflows/Datagen/src/audit/dedup_audit.py` (`main` only)
- Test: `Middleware/Workflows/Datagen/tests/test_description_audit.py`

**Interfaces:**
- Consumes: Task 1 functions; `load_manifest`, `find_duplicates`, `ManifestError`.
- Produces: `main` output adds `Description overlap: <n> descriptions, <pairs> pairs, wording-only mean=<m:.3f> (limit 0.15), same-type >0.5=<p:.2f>% (limit 5%)` and `OVERLAP <message>` per failure. Exit 1 if duplicates or failures.
- Base dir for txt files: the manifest's directory (directory argument, or the file's parent).

- [ ] **Step 1: Write failing tests** (reuse the generator subprocess helper pattern from `test_dedup_audit.py`: 200 records, seed 7, `txt,csv`):
  - `test_generated_run_passes_overlap_limits`: `main == 0`; stdout has `200 descriptions` and `19900 pairs`; the parsed mean is ≤ 0.15 and the percent ≤ 5.
  - `test_near_identical_run_fails` (tmp_path): write 5 txt files from `TEMPLATE` plus a manifest with 5 txt rows (distinct `natural_hash`, `loan_type` "Home Loan") → `main == 1`; stdout has `OVERLAP` and `0 duplicate natural key(s)`.
  - `test_run_without_txt_exits_2`: generator with `--formats csv` → `main == 2`, stderr has `no txt`.
  - `test_duplicates_and_overlap_both_reported`: near-identical fixture plus one duplicated manifest line → `main == 1`; stdout has both `DUPLICATE` and `OVERLAP`.
- [ ] **Step 2: Run** → FAIL (no overlap output).
- [ ] **Step 3: Implement** in `main`: after `load_manifest`, compute `base_dir`; call `load_descriptions` inside the same `ManifestError` → exit 2 block; print the duplicate lines, then the overlap line and the failures.
- [ ] **Step 4: Run** the whole Datagen suite → PASS (S049 tests unchanged, B6).
- [ ] **Step 5: Commit** `S050 #80: run description overlap check in the audit CLI`.

## Self-review

B1 → T1 `test_uses_the_f013_functions` + T2 generated run; B2 → T2 `test_generated_run_passes_overlap_limits`; B3 → T1 `test_near_identical_descriptions_fail` + T2 `test_near_identical_run_fails`; B4 → T1 `test_same_type_limit_checked_alone`, `test_limits_are_inclusive`; B5 → T1 `test_load_descriptions_errors` + T2 `test_run_without_txt_exits_2`; B6 → T2 step 4 (S049 tests) + `test_duplicates_and_overlap_both_reported`; B7 → suite counts. No gaps.

## Review findings (step 9)

Reviewer: fresh general-purpose subagent (opus), range 8cced43..c7f4b10, 2026-11-15.
Verdict: **With fixes**. Critical: none. New tests were 18, not the predicted 13 (parametrized
error cases plus a script-level test).

- **Important #1 — fixed (plan conflict B5 vs B6).** A run without txt exited 2 before the
  duplicate check ran, so S049's check was lost on csv-only runs. Ruling: `main` always
  computes and prints the duplicate result first; missing or bad txt still exits 2 (keeps the
  spec's anti-goal). Test `test_duplicates_reported_even_without_txt` RED→GREEN; suite 78/78.
  B5 in the spec now says this. Also covers Minor #1 (duplicates hidden by a txt error).
- Minor #2 — deferred: duplicate rows pointing to the same txt file inflate the overlap
  figures on a replayed run (the exit is 1 anyway, because of the duplicates).
- Minor #3 — deferred: a `file` value with `..` or an absolute path is read outside the run
  directory (local audit of your own manifest; low risk).
- Minor #4 — deferred: a non-string `file` or `loan_type` is reported as "missing".
- Minor #5 — deferred: the output line types out the limits instead of using the constants.
- Minor #6 — deferred: the output line does not print the same-type pair count.
- Minor #7 — deferred: the "too short" wording means fewer than 5 non-numeric words.
- Declined-to-judge (policy manifests, one-description vacuous pass, O(n²) at 200k, embeddings,
  doc commits, old manifests without loan_type) — ruling: all stand as scoped by the spec.
