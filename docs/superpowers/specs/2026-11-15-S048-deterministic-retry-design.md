# S048 #77 — Deterministic S3 keys + identical DynamoDB upserts on retry (design)

Story: S048 #77 (feature F020 #75, epic E006 #6, milestone M003). The issue
text says "S003 keys"; it means S3 keys (typo, Milestone_003.md §5).
Date: 2026-11-15. Size: small change (tests + one minimal bug fix).

## Intent

DESIGN.md §6.1 / §6.2 and invariants §12.1, §12.3: a shard that failed
half-way and is retried (SQS redrive, no `.done` marker) must regenerate
the same records, land them on the same S3 keys, and upsert DynamoDB
manifest items with identical values, so a retry never creates a
duplicate or a different row. M003 proves this locally with the in-memory
fakes S047 #76 added (`tests/test_batch_worker_markers.py`), no AWS.

## What recon found — a real bug

With the dedup table enabled (F019), the worker claims each record's
natural hash with `PutItem ... ConditionExpression=
attribute_not_exists(natural_hash)` BEFORE uploading. On a retry of a
half-finished shard the retry regenerates the same records, so every
record the failed attempt already claimed now gets a conditional-check
failure and is skipped as a "duplicate" of ITSELF:

- records the failed attempt fully wrote are left out of the retry's
  manifest and marker count (the shard manifest under-reports);
- the record whose claim succeeded but whose upload crashed is lost for
  good — claimed, never written, and skipped on every retry.

So with dedup on, a retry is not identical to a clean run and loses
records. Without dedup the retry is already identical.

Evidence (probe with the S047 fakes, message of 3 records × txt,csv,
crash on the 3rd `put_object`, then retry): clean run → 6 files, marker
`{"files": 6}`; crashed + retried → retry writes 2 files, marker
`{"files": 2}`, only 4 `raw/` objects exist and record 1 has none.

## Goals

- Tests prove: a retry after a mid-shard failure gives exactly the clean
  run's S3 keys, DynamoDB manifest items, shard manifest and marker —
  with dedup off AND with dedup on.
- Minimal fix so a writer re-claiming its OWN hash (same doc_id and same
  loan_id) wins the claim again, while a different record with the same
  natural hash still loses.

## Non-goals

- Byte-identical DOCX/XLSX files: `zipfile.writestr(name, …)` stamps the
  current time into the zip entries, so those bytes can differ between
  attempts. Keys and items are unaffected. Reported as a follow-up, not
  fixed here (outside the story; a generator change needs its own story
  and the uniqueness re-measure, invariant §12.7).
- No change to S3 key format, item shape, or log lines.

## Anti-goals

- A fix that lets a genuine duplicate (same content, different record)
  through.
- A non-atomic read-then-write check (DESIGN.md §6.3: racy across workers).

## Approaches

1. **Self-claim in the condition (chosen).** `claim_natural_hash` uses
   `attribute_not_exists(natural_hash) OR (doc_id = :doc_id AND
   loan_id = :loan_id)` with those two values bound. Still one atomic
   conditional `PutItem`; a retry of the same record re-puts identical
   values; any other record with that hash still fails the condition.
   `doc_id` is `<format>_<idx>` and `loan_id` is derived from the shard
   RNG + idx, so the pair identifies the same generated record.
2. On conditional failure, `get_item` and compare `doc_id`. Two calls,
   needs consistent read, and widens the interface the fake must mimic.
3. Claim after upload, or release claims on failure. Reorders F019's
   "claim before upload" rule, and a crash can still skip the release.

Pick: 1 — developer's call (approval delegated by Kishore for this run):
smallest change, stays atomic, keeps the claim-before-upload order.

## Design

- `src/dedup/natural_hash.py`: `claim_natural_hash` adds the `OR (…)` to
  its `ConditionExpression` and passes `ExpressionAttributeValues=
  {":doc_id": doc_id, ":loan_id": loan_id}`. Signature and return values
  unchanged. Docstring says why.
- Fakes: the dedup fake in `tests/test_natural_hash.py` and in
  `tests/test_batch_worker_markers.py` evaluate the real condition (not a
  string match) — existing hash absent, or stored `doc_id`/`loan_id` equal
  to the bound values.
- New tests in `tests/test_batch_worker_markers.py` (one file holds the
  worker fakes; renaming it is a needless churn) plus one claim test in
  `tests/test_natural_hash.py`.

## Acceptance

1. **Retry = clean run, dedup off.** Clean run on fresh fakes vs a run that
   crashes on the 3rd `put_object` and is then retried on the same fakes:
   identical set of `raw/` S3 keys, identical manifest-table items
   (`doc_id -> item` dict equality), identical shard manifest body and
   marker body.
2. **Retry = clean run, dedup on.** Same comparison with the dedup table
   enabled, including a crash between a claim and its upload: the retry
   writes all `count × formats` files, the marker says `files: 6`, and the
   dedup table holds the same `natural_hash -> item` entries as the clean
   run. (Fails before the fix: the retry skips the records it claimed.)
3. **Retry overwrites with identical values.** Every manifest-table
   `put_item` the retry makes for a doc_id the failed attempt already wrote
   carries a value equal to the first write.
4. **A genuine duplicate still loses.** `claim_natural_hash` with the same
   hash but a different `doc_id` (or a different `loan_id`) returns False
   and leaves the first claim; re-claiming with the same `doc_id` and
   `loan_id` returns True.
5. **Deterministic keys.** Every `raw/` key matches
   `raw/<fmt>/year=YYYY/month=MM/day=DD/loan_<idx:07d>_<loan_id>.<ext>` with
   the record's start date, and two clean runs on fresh fakes give the
   same keys (no timestamp or random suffix — invariant §12.3).
6. **Collected by CI.** Datagen test count rises from 38; DataIndexing 8.

## Left to the builder

- Test names; how the fake parses the condition (it may match the exact
  expression strings the module uses, as long as it applies their meaning).
