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
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

# The worker reads these at import time and builds boto3 clients (no
# network call happens until a client method is used — and every client
# is replaced by a fake below). setdefault never overwrites a real env.
for _name, _value in {
    "CORPUS_BUCKET": "test-corpus-bucket",
    "MANIFEST_TABLE": "test-manifest-table",
    "QUEUE_URL": "https://sqs.invalid/000000000000/test-queue",
    "AWS_REGION": "ap-south-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
}.items():
    os.environ.setdefault(_name, _value)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worker import batch_worker  # noqa: E402

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
    """In-memory DynamoDB table keyed by `key` (doc_id or natural_hash)."""

    def __init__(self, key):
        self.key = key
        self.items = {}
        self.calls = []

    def put_item(self, Item, ConditionExpression=None):
        self.calls.append(dict(Item))
        k = Item[self.key]
        if (ConditionExpression == f"attribute_not_exists({self.key})"
                and k in self.items):
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
    assert len(fakes.s3.objects[MANIFEST].decode().split("\n")) == 6
    assert json.loads(fakes.s3.objects[MARKER]) == {
        "shard_id": "shard-0000", "files": 6}
    assert len(fakes.table.items) == 6


def test_replay_of_marked_shard_writes_nothing(fakes):
    fakes.dedup_on = True
    fakes.install()
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
