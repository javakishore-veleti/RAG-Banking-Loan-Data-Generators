# S048 #77 Deterministic Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove a retried half-finished shard gives the clean run's S3 keys and identical DynamoDB items, and fix the dedup claim so a retry does not skip (and lose) records its own failed attempt claimed.

**Architecture:** `claim_natural_hash` keeps one atomic conditional `PutItem` but also lets the same record re-claim its own hash (`... OR (doc_id = :doc_id AND loan_id = :loan_id)`). The S047 in-memory fakes get a dedup fake that evaluates that condition; new tests compare a clean run with crash+retry on the same fakes.

**Tech Stack:** Python 3.12, pytest, botocore `ClientError`.

**Spec:** `docs/superpowers/specs/2026-11-15-S048-deterministic-retry-design.md`

## Global Constraints

- No new dependencies, no network, no AWS; fakes hand-written.
- `batch_worker.py` unchanged. Only `src/dedup/natural_hash.py::claim_natural_hash` changes (condition + bound values); signature `claim_natural_hash(table, hash_value, doc_id, loan_id) -> bool` unchanged; item shape `{"natural_hash", "doc_id", "loan_id"}` unchanged.
- Exact condition: `attribute_not_exists(natural_hash) OR (doc_id = :doc_id AND loan_id = :loan_id)`, `ExpressionAttributeValues={":doc_id": doc_id, ":loan_id": loan_id}`. Expose it as module constant `CLAIM_CONDITION`.
- Message as in S047: `MSG` from `tests/test_batch_worker_markers.py` (3 records × txt,csv); crash via `FakeS3(fail_on_put=3)` (record 1 is claimed, its first upload crashes).
- Suite counts: Datagen 38 → 38 + new; DataIndexing 8.
- Commits `S048 #77: <imperative summary>`, author Kishore, no AI trailer.

## Review Focus

1. A genuine duplicate (same hash, different doc_id, or same doc_id but different loan_id) must still lose → `test_claim_same_record_reclaims_other_record_loses` (Task 1).
2. Fakes must apply the condition's meaning, not accept anything: both dedup fakes raise `ConditionalCheckFailedException` unless the hash is absent or the stored doc_id AND loan_id equal the bound values; an unknown ConditionExpression raises `AssertionError` (Task 1).
3. Within one shard, two different idx with equal content: second still skipped → covered by item 1 at unit level (doc_id differs).
4. Retry's DynamoDB overwrite values equal the first write (not just the final state) → `test_retry_rewrites_identical_manifest_items` (Task 2).
5. Keys carry no timestamp/random suffix → `test_raw_keys_are_deterministic` regex + two clean runs equal (Task 2).

---

### Task 1: Self-claim fix in `claim_natural_hash` (Acceptance 2, 4)

**Files:**
- Modify: `Middleware/Workflows/Datagen/src/dedup/natural_hash.py` (`claim_natural_hash`, new `CLAIM_CONDITION`, docstring)
- Modify: `Middleware/Workflows/Datagen/tests/test_natural_hash.py` (`FakeTable.put_item` evaluates the condition; new test)
- Modify: `Middleware/Workflows/Datagen/tests/test_batch_worker_markers.py` (`FakeTable.put_item` same evaluation; new worker test)

**Interfaces:**
- Produces: `natural_hash.CLAIM_CONDITION: str`; fakes' `put_item(Item, ConditionExpression=None, ExpressionAttributeValues=None)`; helper in markers test `_run_clean(dedup_on: bool) -> SimpleNamespace` and `_run_crash_then_retry(dedup_on: bool) -> SimpleNamespace` returning the fakes after the run (used in Task 2).

- [x] **Step 1: Write the failing tests**
  - `test_natural_hash.py::test_claim_same_record_reclaims_other_record_loses`: claim(h, "pdf_0000000", "LN1") is True; same call again is True; (h, "pdf_0000001", "LN1") is False; (h, "pdf_0000000", "LN2") is False; stored item still `doc_id == "pdf_0000000"`, `loan_id == "LN1"`.
  - `test_batch_worker_markers.py::test_retry_with_dedup_matches_clean_run`: `clean = _run_clean(True)`, `retry = _run_crash_then_retry(True)`; retry's second `process_shard` returned 6; marker bodies equal `{"shard_id": "shard-0000", "files": 6}`; `raw/` key sets equal; `table.items` equal; `dedup.items` equal; manifest bodies equal.
- [x] **Step 2: Run** — Expected: both FAIL (re-claim returns False; retry returns 2, marker `files: 2`).
- [x] **Step 3: Implement** the condition + `ExpressionAttributeValues` in `claim_natural_hash`; docstring states a retry of the same record wins its own claim.
- [x] **Step 4: Run both suites** — Datagen 40 passed, DataIndexing 8 passed.
- [x] **Step 5: Commit** `S048 #77: let a retried record re-claim its own natural hash`, push.

### Task 2: Retry determinism without dedup + key format (Acceptance 1, 3, 5)

**Files:**
- Modify: `Middleware/Workflows/Datagen/tests/test_batch_worker_markers.py`

**Interfaces:**
- Consumes: `_run_clean`, `_run_crash_then_retry` from Task 1; `FakeTable.calls`.

- [x] **Step 1: Write the tests**
  - `test_retry_without_dedup_matches_clean_run`: as the dedup test with `dedup_on=False` (raw keys, table items, manifest, marker equal).
  - `test_retry_rewrites_identical_manifest_items`: in `_run_crash_then_retry(False)`, for each doc_id, every entry in `table.calls` with that doc_id equals the final `table.items[doc_id]` (and at least one doc_id was written twice).
  - `test_raw_keys_are_deterministic`: for each manifest row of a clean run, `s3_key == f"raw/{fmt}/year={y}/month={m:02d}/day={d:02d}/loan_{idx:07d}_{loan_id}.{fmt}"` with `fmt`, `idx` from `doc_id`, `y/m/d` from the row, and `loan_id` matching `^\d{12}$` (loan_id is `LN<6><6>`[-12:], all digits); two `_run_clean(False)` runs give equal sorted `raw/` key lists.
- [x] **Step 2: Run** — Expected: pass (behaviour exists). RED by mutation: temporarily append `f"_{time.time_ns()}"` to `fname` in the worker → key tests fail; restore with `git checkout --`.
- [x] **Step 3: Run both suites** — Datagen 43 passed, DataIndexing 8 passed.
- [x] **Step 4: Commit** `S048 #77: test retry gives identical keys and manifest items`, push.

## Ledger
- Ruling: executed inline with superpowers:executing-plans, not subagent-driven — two small tasks sharing one test file's fakes and helpers (tightly coupled); a fresh reviewer subagent reviews the branch at step 9 — cost if wrong: no per-task review gate.
- Task 1 BASE 6d98888. RED stage 1: ImportError (`CLAIM_CONDITION` missing). RED stage 2 (constant = old condition): `test_retry_with_dedup_matches_clean_run` fails `assert 2 == 6`, `test_claim_same_record_reclaims_other_record_loses` fails on the re-claim (False). GREEN after the self-claim condition: Datagen 40, DataIndexing 8.
- Ruling: also updated the F019 comment in `batch_worker.py` (comment only, no code) and DESIGN.md §6.3 step 4 — both described the old claim and would now mislead — cost if wrong: two doc lines to revert.
- Task 1: complete (commits 6d98888..3013695).
- Task 2 BASE 3013695. 3 tests green against current code. RED by mutation: (a) `_{time.time_ns()}` appended to the file name → 4 tests fail (both retry-equality tests, identical-rewrite, key format); (b) a wall-clock `"t"` field in the manifest row → 3 tests fail (retry equality ×2, identical rewrite). Worker restored. Datagen 43, DataIndexing 8.
- Task 2: complete (this commit).
