"""F020 / S047 #76 — shard `.done` marker tests for the batch worker.

DESIGN.md §6.1 and invariant §12.4: a shard that finishes writes
markers/<run_id>/<shard_id>.done LAST; a shard with a marker is skipped
on replay; a shard without a marker is not finished, even if some of its
files exist. The SQS message is deleted only after the shard succeeds.

M003 closes on local proof (Milestone_003.md §5): these tests import the
real worker and replace its module-level AWS clients with hand-written
in-memory fakes. No moto, no network, no AWS.
"""
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

# The worker reads these at import time and builds boto3 clients (no
# network call happens until a client method is used — and every client
# is replaced by a fake below). Only names not already set are added, and
# they are removed again right after the import so they cannot leak into
# other test files.
_DUMMY_ENV = {
    "CORPUS_BUCKET": "test-corpus-bucket",
    "MANIFEST_TABLE": "test-manifest-table",
    "QUEUE_URL": "https://sqs.invalid/000000000000/test-queue",
    "AWS_REGION": "ap-south-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
}
_ADDED_ENV = [n for n in _DUMMY_ENV if n not in os.environ]
for _name in _ADDED_ENV:
    os.environ[_name] = _DUMMY_ENV[_name]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worker import batch_worker  # noqa: E402
from tests.test_natural_hash import claim_allowed  # noqa: E402

for _name in _ADDED_ENV:
    os.environ.pop(_name, None)

MSG = {"shard_id": "shard-0000", "start": 0, "count": 3,
       "formats": ["txt", "csv"], "year": 2024, "seed": 7, "run_id": "t-run"}
MARKER = "markers/t-run/shard-0000.done"
MANIFEST = "manifests/t-run/shard-0000.jsonl"


def _client_error(code, op):
    return ClientError({"Error": {"Code": code, "Message": code}}, op)


class FakeS3:
    """In-memory S3: only the two calls the worker makes."""

    def __init__(self, fail_on_put=None, head_error=None):
        self.objects = {}          # key -> body bytes
        self.puts = []             # keys, in put order
        self.fail_on_put = fail_on_put
        self.head_error = head_error

    def head_object(self, Bucket, Key):
        if self.head_error:
            raise _client_error(self.head_error, "HeadObject")
        if Key not in self.objects:
            raise _client_error("404", "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType):
        if self.fail_on_put is not None and len(self.puts) + 1 == self.fail_on_put:
            raise RuntimeError(f"simulated crash on put #{self.fail_on_put}")
        self.objects[Key] = Body
        self.puts.append(Key)
        return {}


class _ConditionalCheckFailed(Exception):
    def __init__(self):
        super().__init__("The conditional request failed")
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeTable:
    """In-memory DynamoDB table keyed by `key` (doc_id or natural_hash).
    For the dedup table it applies the meaning DynamoDB gives the claim
    condition (claim_allowed in test_natural_hash: literal expressions,
    not the module's constant)."""

    def __init__(self, key):
        self.key = key
        self.items = {}
        self.calls = []

    def put_item(self, Item, ConditionExpression=None,
                 ExpressionAttributeValues=None):
        self.calls.append(dict(Item))
        k = Item[self.key]
        if ConditionExpression is not None and not claim_allowed(
                ConditionExpression, ExpressionAttributeValues,
                self.items.get(k)):
            raise _ConditionalCheckFailed()
        self.items[k] = dict(Item)
        return {}


class FakeSQS:
    """One message, then an empty poll so main() exits."""

    def __init__(self, body):
        self._pending = [{"Body": json.dumps(body), "ReceiptHandle": "rh-1"}]
        self.deleted = []

    def receive_message(self, **kwargs):
        if self._pending:
            return {"Messages": [self._pending.pop(0)]}
        return {}

    def delete_message(self, QueueUrl, ReceiptHandle):
        self.deleted.append(ReceiptHandle)
        return {}


@pytest.fixture
def fakes(monkeypatch):
    ns = SimpleNamespace(s3=FakeS3(), table=FakeTable("doc_id"),
                         dedup=FakeTable("natural_hash"), sqs=FakeSQS(MSG))

    def install(**overrides):
        for name, value in overrides.items():
            setattr(ns, name, value)
        monkeypatch.setattr(batch_worker, "s3", ns.s3)
        monkeypatch.setattr(batch_worker, "table", ns.table)
        monkeypatch.setattr(batch_worker, "sqs", ns.sqs)
        # Dedup is off unless a test opts in with install(dedup_on=True).
        monkeypatch.setattr(batch_worker, "dedup_table",
                            ns.dedup if ns.dedup_on else None)
        return ns

    ns.dedup_on = False
    ns.install = install
    monkeypatch.setattr(batch_worker.time, "sleep", lambda s: None)
    return install()


def test_fresh_shard_writes_files_then_marker_last(fakes):
    assert batch_worker.process_shard(dict(MSG)) == 6
    raw = [k for k in fakes.s3.puts if k.startswith("raw/")]
    assert len(raw) == 6
    assert fakes.s3.puts[-2] == MANIFEST
    assert fakes.s3.puts[-1] == MARKER
    assert fakes.s3.puts.count(MARKER) == 1  # written once, after all data
    rows = [json.loads(line)
            for line in fakes.s3.objects[MANIFEST].decode().split("\n")]
    assert len(rows) == 6
    # The shard manifest lists exactly the rows upserted to DynamoDB.
    assert {r["doc_id"] for r in rows} == set(fakes.table.items)
    assert json.loads(fakes.s3.objects[MARKER]) == {
        "shard_id": "shard-0000", "files": 6}
    assert len(fakes.table.items) == 6


def test_replay_of_marked_shard_writes_nothing(fakes):
    fakes.install(dedup_on=True)
    fakes.s3.objects[MARKER] = b'{"shard_id": "shard-0000", "files": 6}'
    assert batch_worker.process_shard(dict(MSG)) == 0
    assert fakes.s3.puts == []
    assert fakes.table.calls == []
    assert fakes.dedup.calls == []


def test_marker_check_other_error_raises(fakes):
    fakes.install(s3=FakeS3(head_error="403"))
    with pytest.raises(ClientError):
        batch_worker.process_shard(dict(MSG))
    assert fakes.s3.puts == []


def test_failed_shard_writes_no_marker_then_rerun_finishes(fakes):
    fakes.install(s3=FakeS3(fail_on_put=3))
    with pytest.raises(RuntimeError):
        batch_worker.process_shard(dict(MSG))
    assert MARKER not in fakes.s3.objects
    assert MANIFEST not in fakes.s3.objects
    # Some files exist, but without a marker the shard is not finished.
    assert len([k for k in fakes.s3.objects if k.startswith("raw/")]) == 2

    fakes.s3.fail_on_put = None
    assert batch_worker.process_shard(dict(MSG)) == 6
    assert fakes.s3.puts[-1] == MARKER
    assert json.loads(fakes.s3.objects[MARKER])["files"] == 6
    assert MANIFEST in fakes.s3.objects


def test_main_deletes_message_after_success(fakes):
    assert batch_worker.main() == 0
    assert fakes.sqs.deleted == ["rh-1"]
    assert MARKER in fakes.s3.objects


def test_main_keeps_message_when_shard_fails(fakes):
    fakes.install(s3=FakeS3(fail_on_put=1))
    assert batch_worker.main() == 0
    # Message stays visible: SQS redrives it, then DLQ (invariant §12.5).
    assert fakes.sqs.deleted == []
    assert MARKER not in fakes.s3.objects


def test_main_deletes_message_on_replay_of_marked_shard(fakes):
    fakes.s3.objects[MARKER] = b'{"shard_id": "shard-0000", "files": 6}'
    assert batch_worker.main() == 0
    assert fakes.sqs.deleted == ["rh-1"]
    assert fakes.s3.puts == []


# ---------------------------------------------------------------- S048 #77
# A retried shard (crashed half-way, no marker) must give exactly the
# clean run's S3 keys and DynamoDB items (DESIGN.md §6.1, §12.1, §12.3).

def _run_clean(dedup_on):
    ns = SimpleNamespace(s3=FakeS3(), table=FakeTable("doc_id"),
                         dedup=FakeTable("natural_hash"))
    _wire(ns, dedup_on)
    ns.returned = batch_worker.process_shard(dict(MSG))
    return ns


def _run_crash_then_retry(dedup_on):
    # Crash on the 3rd put: record 0 is fully written, record 1 is
    # claimed (when dedup is on) but its first upload fails.
    ns = SimpleNamespace(s3=FakeS3(fail_on_put=3), table=FakeTable("doc_id"),
                         dedup=FakeTable("natural_hash"))
    _wire(ns, dedup_on)
    with pytest.raises(RuntimeError):
        batch_worker.process_shard(dict(MSG))
    ns.s3.fail_on_put = None
    ns.returned = batch_worker.process_shard(dict(MSG))
    return ns


def _wire(ns, dedup_on):
    # Plain assignment is safe: callers use the `fakes` fixture, whose
    # monkeypatch restores these globals after the test.
    batch_worker.s3 = ns.s3
    batch_worker.table = ns.table
    batch_worker.dedup_table = ns.dedup if dedup_on else None


def _raw_keys(ns):
    return sorted(k for k in ns.s3.objects if k.startswith("raw/"))


def test_retry_with_dedup_matches_clean_run(fakes):
    clean = _run_clean(True)
    retry = _run_crash_then_retry(True)
    assert retry.returned == clean.returned == 6
    assert json.loads(retry.s3.objects[MARKER]) == {
        "shard_id": "shard-0000", "files": 6}
    assert retry.s3.objects[MARKER] == clean.s3.objects[MARKER]
    assert _raw_keys(retry) == _raw_keys(clean)
    assert retry.table.items == clean.table.items
    assert retry.dedup.items == clean.dedup.items
    assert retry.s3.objects[MANIFEST] == clean.s3.objects[MANIFEST]


def test_retry_without_dedup_matches_clean_run(fakes):
    clean = _run_clean(False)
    retry = _run_crash_then_retry(False)
    assert retry.returned == clean.returned == 6
    assert retry.s3.objects[MARKER] == clean.s3.objects[MARKER]
    assert _raw_keys(retry) == _raw_keys(clean)
    assert retry.table.items == clean.table.items
    assert retry.s3.objects[MANIFEST] == clean.s3.objects[MANIFEST]


def test_retry_rewrites_identical_manifest_items(fakes):
    retry = _run_crash_then_retry(False)
    rewritten = 0
    for doc_id, final in retry.table.items.items():
        writes = [c for c in retry.table.calls if c["doc_id"] == doc_id]
        assert all(w == final for w in writes), doc_id
        rewritten += len(writes) > 1
    # Record 0 (txt + csv) was written by the failed attempt and again
    # by the retry, with identical values.
    assert rewritten == 2


def test_raw_keys_are_deterministic(fakes):
    clean = _run_clean(False)
    rows = [json.loads(line)
            for line in clean.s3.objects[MANIFEST].decode().split("\n")]
    assert len(rows) == 6
    for r in rows:
        fmt, idx = r["doc_id"].split("_")
        assert re.fullmatch(r"\d{12}", r["loan_id"]), r["loan_id"]
        assert r["s3_key"] == (
            f"raw/{fmt}/year={r['year']}/month={r['month']:02d}/"
            f"day={r['day']:02d}/loan_{idx}_{r['loan_id']}.{fmt}")
        assert r["s3_key"] in clean.s3.objects
    # A second clean run on fresh fakes lands on exactly the same keys.
    assert _raw_keys(_run_clean(False)) == _raw_keys(clean)


def test_hash_claimed_by_another_record_is_still_skipped(fakes):
    # A genuine duplicate: record 0's hash is held by a different doc_id
    # (another record with the same content). The retry fix must not let
    # it through: record 0 is skipped in both formats.
    first = _run_clean(True)
    rec0 = next(v for v in first.dedup.items.values()
                if v["doc_id"] == "txt_0000000")
    dedup = FakeTable("natural_hash")
    dedup.items = {h: dict(v) for h, v in first.dedup.items.items()}
    dedup.items[rec0["natural_hash"]]["doc_id"] = "txt_0999999"
    ns = SimpleNamespace(s3=FakeS3(), table=FakeTable("doc_id"), dedup=dedup)
    _wire(ns, True)
    assert batch_worker.process_shard(dict(MSG)) == 4
    assert json.loads(ns.s3.objects[MARKER])["files"] == 4
    assert not any("loan_0000000_" in k for k in ns.s3.objects)
    assert "txt_0000000" not in ns.table.items
