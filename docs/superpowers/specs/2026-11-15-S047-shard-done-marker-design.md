# S047 #76 — Shard `.done` marker: replay skips finished shards (design)

Story: S047 #76 (feature F020 #75, epic E006 #6, milestone M003).
Date: 2026-11-15. Size: small change (tests only, no production change).

## Intent

DESIGN.md §6.1 and invariant §12.4 say: a shard that finishes writes
`markers/<run_id>/<shard_id>.done`; a shard with a marker is skipped on
replay; a shard without a marker is not finished, even if some of its
files exist. `Middleware/Workflows/Datagen/src/worker/batch_worker.py`
already has this code, but nothing tests it. M003 closes on LOCAL proof
(Milestone_003.md §5 decision, 2026-11-15): prove the behaviour with unit
tests of the worker using hand-written in-memory fakes for S3, DynamoDB
and SQS. No moto, no new dependency, no network, no AWS.

## Goals

- Tests that run `process_shard` and `main` from `batch_worker.py` against
  in-memory fakes and prove the marker behaviour (Acceptance below).
- Tests are collected by the CI command
  `python -m pytest Middleware/Workflows/Datagen/tests/ -q`
  (count goes from 31 up).

## Non-goals

- No change to the worker's production behaviour, its S3 keys, its
  DynamoDB items or its log lines. No refactor.
- Retry determinism of keys / items and dedup-claim-on-retry are S048 #77.
- No live AWS run (moved to M004 exit criteria).

## Anti-goals

- A test that passes without exercising the real worker code (e.g. tests a
  copy of the logic) — the tests must import and call `batch_worker`.
- A test that could reach AWS: every client the worker uses is replaced.

## Constraints

- `batch_worker.py` reads `CORPUS_BUCKET`, `MANIFEST_TABLE`, `QUEUE_URL`
  from the environment and builds boto3 clients at import time. boto3 is
  in `requirements.txt` and in the local venv (1.44.3), so the module can
  be imported once fake env values are set; creating a boto3 client does
  not touch the network.
- Fakes are hand-written in the test file. botocore's `ClientError` is
  used for the 404 the fake S3 raises on `head_object`, because the worker
  checks `e.response["Error"]["Code"]` on a `ClientError`.

## Approaches

1. **Use the module's existing globals as the seam (chosen).** Set dummy
   env values with `os.environ.setdefault` before import, then
   `monkeypatch.setattr(batch_worker, "s3" | "table" | "dedup_table" | "sqs", fake)`.
   Zero production change; production behaviour identical by construction.
2. Add keyword parameters (`process_shard(msg, s3=None, table=None, ...)`).
   Cleaner injection, but changes the signature and every call site for no
   runtime benefit; the module globals already are an injection point.
3. Wrap the worker in a class with injected clients. A refactor the story
   does not need; rejected (no drive-by refactors).

Pick: 1 — decided by the developer (approval delegated by Kishore for
this run): it proves the existing code without touching it.

## Design

New test file `Middleware/Workflows/Datagen/tests/test_batch_worker_markers.py`:

- Before import: `os.environ.setdefault` for `CORPUS_BUCKET`,
  `MANIFEST_TABLE`, `QUEUE_URL`, `AWS_REGION`, plus dummy
  `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`; add `src` to `sys.path`
  like the other tests; `from worker import batch_worker`.
- `FakeS3`: dict of `key -> (body, content_type)` plus an ordered list of
  every `put_object` key; `head_object` raises `ClientError` code `404`
  when missing; optional `fail_on_put=n` raises on the n-th put (simulates
  a crash mid-shard).
- `FakeTable`: dict `doc_id -> item` plus a call log for `put_item`;
  for the dedup table, keyed by `natural_hash` and honouring
  `ConditionExpression="attribute_not_exists(natural_hash)"`.
- `FakeSQS`: one queued message, records `delete_message` calls; returns
  no messages on the second receive so `main()` exits.
- A pytest fixture wires the fakes into `batch_worker` with `monkeypatch`
  (and patches `time.sleep` so the failure path does not wait 5 s).
- Message used: `{"shard_id": "shard-0000", "start": 0, "count": 3,
  "formats": ["txt", "csv"], "year": 2024, "seed": 7, "run_id": "t-run"}`
  (cheap formats, no Pillow; two formats exercise the per-format loop).

## Acceptance

1. **Fresh shard writes everything, marker last.** With no marker,
   `process_shard` returns `count × len(formats)` (6), puts 6 data objects
   under `raw/`, the manifest `manifests/t-run/shard-0000.jsonl` with 6 lines,
   then `markers/t-run/shard-0000.done` as the LAST `put_object`; the marker
   body is `{"shard_id": "shard-0000", "files": 6}`; 6 manifest rows are in
   the DynamoDB fake.
2. **Replay of a finished shard writes nothing.** When the marker exists,
   `process_shard` returns 0 and makes no S3 `put_object`, no manifest-table
   `put_item` and no dedup claim (dedup table enabled in this test).
3. **A shard that fails mid-way writes no marker.** With the fake S3 failing
   on the 3rd `put_object`, `process_shard` raises, and neither the marker
   nor the manifest exists; the data objects already put stay (a shard
   without a marker is not finished even if some files exist).
4. **A shard without a marker runs even if some of its files exist.** After
   the failed attempt in 3, a second `process_shard` on the same fakes runs
   the shard to completion and writes the marker.
5. **SQS message is deleted only after the shard succeeds.** `main()` with a
   fake SQS: success → `delete_message` called once with the receipt
   handle; shard failure → `delete_message` never called; replay of a
   marked shard → message deleted (the replay is a success).
6. **Collected by CI.** The Datagen suite count rises from 31 by the number
   of new tests; DataIndexing stays at 8.

## Left to the builder

- Exact test names and fake internals; whether 3 and 4 are one test or two.
