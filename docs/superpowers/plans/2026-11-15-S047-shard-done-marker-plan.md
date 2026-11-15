# S047 #76 Shard `.done` Marker Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove with local unit tests that the batch worker writes the shard `.done` marker last, skips a marked shard on replay, never writes a marker for a failed shard, and acks SQS only on success.

**Architecture:** One new pytest file imports the real `worker.batch_worker` (dummy env values set before import) and replaces its module globals `s3`, `table`, `dedup_table`, `sqs` with hand-written in-memory fakes via `monkeypatch`. No production code changes.

**Tech Stack:** Python 3.12, pytest, botocore `ClientError` (already a dependency via boto3).

**Spec:** `docs/superpowers/specs/2026-11-15-S047-shard-done-marker-design.md`

## Global Constraints

- No new dependencies (no moto); fakes are hand-written; no network, no AWS.
- `Middleware/Workflows/Datagen/src/worker/batch_worker.py` production behaviour unchanged (no edits planned).
- Tests must be collected by `python -m pytest Middleware/Workflows/Datagen/tests/ -q` (31 → 31 + new); DataIndexing stays 8.
- Test message: `{"shard_id": "shard-0000", "start": 0, "count": 3, "formats": ["txt", "csv"], "year": 2024, "seed": 7, "run_id": "t-run"}`.
- Marker key `markers/t-run/shard-0000.done`, manifest key `manifests/t-run/shard-0000.jsonl`.
- Commits: `S047 #76: <imperative summary>`, author Kishore from git config, no AI trailer.

## Review Focus

1. Env leakage: dummy `CORPUS_BUCKET` etc. set with `setdefault` so a real env is never overwritten, and no real boto3 call is made — every global the worker touches is replaced in the fixture (`s3`, `table`, `dedup_table`, `sqs`). Pinned by Task 1 fixture; FakeS3 raises on any unexpected method because it only defines `head_object` / `put_object`.
2. A non-404 `head_object` error must propagate, not be treated as "not done" — pinned by `test_marker_check_other_error_raises` in Task 1.
3. Tests must fail when the marker logic breaks — each task's RED step is a mutation check (temporarily break the worker line, watch the test fail, restore with `git checkout`).
4. Replay with dedup enabled must not claim hashes (a claim on replay would mark finished records as duplicates) — pinned by Acceptance 2 test with `dedup_table` set.
5. `main()` failure path sleeps 5 s — `time.sleep` is patched so the suite stays fast.

---

### Task 1: Fakes + `process_shard` marker tests (Acceptance 1–4)

**Files:**
- Create: `Middleware/Workflows/Datagen/tests/test_batch_worker_markers.py`

**Interfaces:**
- Produces (used by Task 2, same file): `FakeS3(fail_on_put: int | None = None)` with `.objects: dict[str, bytes]`, `.puts: list[str]` (keys in put order), `head_object(Bucket, Key)`, `put_object(Bucket, Key, Body, ContentType)`; `FakeTable(key: str)` with `.items: dict`, `.calls: list[dict]`, `put_item(Item, ConditionExpression=None)`; fixture `fakes(monkeypatch) -> SimpleNamespace(s3, table, dedup)` that patches `batch_worker.s3`, `.table`, `.dedup_table` (to `None` by default; tests opt in), `.sqs`, and `batch_worker.time.sleep`; constant `MSG` (Global Constraints message).

- [ ] **Step 1: Write the tests**
  - `test_fresh_shard_writes_files_then_marker_last`: `process_shard(dict(MSG)) == 6`; 6 keys in `s3.puts` start with `raw/`; `s3.puts[-2] == "manifests/t-run/shard-0000.jsonl"` with 6 JSON lines; `s3.puts[-1] == "markers/t-run/shard-0000.done"`; `json.loads(marker) == {"shard_id": "shard-0000", "files": 6}`; `len(table.items) == 6`.
  - `test_replay_of_marked_shard_writes_nothing`: dedup table enabled; pre-seed marker in `s3.objects`; reset `s3.puts`; `process_shard == 0`; `s3.puts == []`, `table.calls == []`, `dedup.calls == []`.
  - `test_marker_check_other_error_raises`: `head_object` raising `ClientError` code `403` → `process_shard` raises `ClientError`, no puts.
  - `test_failed_shard_writes_no_marker_then_rerun_finishes`: `FakeS3(fail_on_put=3)` → `pytest.raises(RuntimeError)`; marker and manifest absent; 2 `raw/` objects present; clear `fail_on_put`; rerun returns 6 and marker exists.
- [ ] **Step 2: Run** `.../runtime_data/venv/bin/python -m pytest Middleware/Workflows/Datagen/tests/test_batch_worker_markers.py -v` — Expected: 4 passed (code exists).
- [ ] **Step 3: RED by mutation** — temporarily (a) move the marker `put_object` above the record loop and (b) replace the head-check `return 0` with `pass`; run; Expected: fresh-shard / failed-shard tests fail under (a), replay test fails under (b). Restore with `git checkout -- Middleware/Workflows/Datagen/src/worker/batch_worker.py`; `git diff --stat` shows no worker change.
- [ ] **Step 4: Run both suites** — Datagen `35 passed`, DataIndexing `8 passed`.
- [ ] **Step 5: Commit** `S047 #76: test shard marker written last and replay skip` (stage the test file by name), push.

### Task 2: `main()` acks SQS only after success (Acceptance 5)

**Files:**
- Modify: `Middleware/Workflows/Datagen/tests/test_batch_worker_markers.py`

**Interfaces:**
- Consumes: `FakeS3`, `fakes` fixture, `MSG` from Task 1.
- Produces: `FakeSQS(body: dict)` — `receive_message(**kw)` returns `{"Messages": [{"Body": json.dumps(body), "ReceiptHandle": "rh-1"}]}` once, then `{}`; `.deleted: list[str]` of receipt handles.

- [ ] **Step 1: Write the tests**
  - `test_main_deletes_message_after_success`: `main() == 0`; `sqs.deleted == ["rh-1"]`; marker exists.
  - `test_main_keeps_message_when_shard_fails`: `FakeS3(fail_on_put=1)`; `main() == 0`; `sqs.deleted == []`; no marker.
  - `test_main_deletes_message_on_replay_of_marked_shard`: marker pre-seeded; `main() == 0`; `sqs.deleted == ["rh-1"]`; no `put_object`.
- [ ] **Step 2: Run** the file — Expected: 7 passed.
- [ ] **Step 3: RED by mutation** — temporarily move `sqs.delete_message(...)` above the `try:`; Expected: `test_main_keeps_message_when_shard_fails` fails. Restore with `git checkout --`.
- [ ] **Step 4: Run both suites** — Datagen `38 passed`, DataIndexing `8 passed`.
- [ ] **Step 5: Commit** `S047 #76: test SQS ack only after shard success`, push.

## Ledger

(Execution record; rulings as `Ruling: <what> — <why> — <cost if wrong>`.)
- Ruling: executed inline with superpowers:executing-plans, not subagent-driven — both tasks share one test file's fakes (tightly coupled) and the plan is small; a fresh reviewer subagent reviews the whole branch at step 9 — cost if wrong: no per-task review gate.
- Task 1 BASE 6b3b6f1. 4 tests green against unchanged worker. RED by mutation: (a) marker put before the loop → fresh-shard (after adding `puts.count(MARKER) == 1`) and failed-shard tests fail; (b) replay `return 0` → `pass` → replay test fails; (c) non-404 `raise` → `pass` → 403 test fails. Worker restored (`git diff` empty). Datagen 35 passed, DataIndexing 8 passed.
- Ruling: added `assert fakes.s3.puts.count(MARKER) == 1` to the fresh-shard test — mutation (a) showed "last" alone misses an early extra marker — cost if wrong: none (stricter).
