#!/usr/bin/env python3
"""
Batch worker — one shard = one SQS message.

Message body (JSON) — one document type, one year, per run:
  {"shard_id": "shard-0000", "start": 0, "count": 10000,
   "formats": ["pdf"], "year": 2024,
   "seed": 7, "run_id": "2024-pdf-001"}

Behaviour:
  - Polls SQS (long poll, batch of 1 message at a time — a shard is big).
  - Generates records deterministically from `seed` + `start` + `year`,
    so a retry produces identical files (idempotent).
  - Uploads each file to S3, partitioned yyyy/mm/dd by loan start date:
    s3://<BUCKET>/raw/<format>/year=2024/month=03/day=12/loan_<idx>_<loan_id>.<ext>
  - Upserts manifest rows to DynamoDB (doc_id = "<format>_<idx>").
  - Claims each record's natural hash in the dedup table before
    uploading (F019); a hash already claimed means a duplicate loan,
    and its files are skipped entirely.
  - Writes a shard manifest to S3:  s3://<BUCKET>/manifests/<run_id>/<shard_id>.jsonl
  - Writes a completion marker:   s3://<BUCKET>/markers/<run_id>/<shard_id>.done
    (Step Functions checks markers; a shard with a marker is skipped on replay.)
  - Deletes the SQS message ONLY after the whole shard succeeds.
    Any exception -> message stays visible, SQS redrives it, then DLQ.

Env: CORPUS_BUCKET, MANIFEST_TABLE, QUEUE_URL, AWS_REGION
Optional: DEDUP_TABLE (dedup table name; claiming is skipped when unset,
so existing deployments without it keep working — add it to the Batch
job definition env to enable F019 dedup, see DESIGN.md §6).
Requires: boto3. Generator itself has no external deps.
Shared bottom layer: this worker is format-agnostic. The only thing that
changes per document type is msg["formats"] = ["pdf"] (or ["docx"], …).
All six format workflows reuse this same worker, the same generator
(src/generator/generator.py), and the same Batch job definition.
"""
import io
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from generator.generator import make_record, answer_for, WRITERS  # noqa: E402
from dedup.natural_hash import claim_natural_hash  # noqa: E402

BUCKET = os.environ["CORPUS_BUCKET"]
TABLE = os.environ["MANIFEST_TABLE"]
DEDUP_TABLE_NAME = os.environ.get("DEDUP_TABLE")
QUEUE_URL = os.environ["QUEUE_URL"]
REGION = os.environ.get("AWS_REGION", "ap-south-1")

RETRY = Config(retries={"max_attempts": 5, "mode": "adaptive"})
s3 = boto3.client("s3", region_name=REGION, config=RETRY)
sqs = boto3.client("sqs", region_name=REGION, config=RETRY)
ddb = boto3.resource("dynamodb", region_name=REGION, config=RETRY)
table = ddb.Table(TABLE)
dedup_table = ddb.Table(DEDUP_TABLE_NAME) if DEDUP_TABLE_NAME else None


def _upload_bytes(key: str, data: bytes, content_type: str) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=content_type)


CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv", "txt": "text/plain", "png": "image/png",
}


def process_shard(msg: dict) -> int:
    run_id = msg["run_id"]
    shard_id = msg["shard_id"]
    marker = f"markers/{run_id}/{shard_id}.done"
    try:
        s3.head_object(Bucket=BUCKET, Key=marker)
        print(f"Shard {shard_id} already done, skipping (idempotent replay).")
        return 0
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchKey"):
            raise

    import random
    # Deterministic per shard: seed + start + year. A retry reproduces identical files.
    year = msg.get("year") or 0
    rng = random.Random(int(msg.get("seed", 7)) * 1_000_003 + int(msg["start"]) + int(year) * 10_007)

    manifest_lines = []
    written = 0
    skipped = 0
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for idx in range(msg["start"], msg["start"] + msg["count"]):
            rec = make_record(rng, idx, year=msg.get("year"))
            if dedup_table is not None and msg["formats"]:
                # F019: claim the natural hash ONCE per record, before any
                # format is written. The hash identifies the loan content,
                # not one file, so all formats of a duplicate are skipped
                # together. A crash between claim and upload leaves the
                # hash claimed with no file — the generator samples unique
                # tuples without replacement, so a re-run with a fresh
                # seed does not re-emit the same content (DESIGN.md §6).
                if not claim_natural_hash(
                        dedup_table, rec["natural_hash"],
                        f"{msg['formats'][0]}_{idx:07d}", rec["loan_id"]):
                    print(f"Skipped duplicate {rec['loan_id']} "
                          f"hash {rec['natural_hash']}")
                    skipped += len(msg["formats"])
                    continue
            ans = answer_for(rec)
            for fmt in msg["formats"]:
                ext, writer = WRITERS[fmt]
                fname = f"loan_{idx:07d}_{rec['loan_id']}.{ext}"
                local = tmp / fname
                writer(local, rec)
                # yyyy/mm/dd partition by loan start date (Hive-style).
                y, m, d = rec["start_date"].split("-")
                key = f"raw/{fmt}/year={y}/month={m}/day={d}/{fname}"
                _upload_bytes(key, local.read_bytes(), CONTENT_TYPES[fmt])
                row = {
                    "doc_id": f"{fmt}_{idx:07d}", "format": fmt, "s3_key": key,
                    "loan_id": rec["loan_id"], "loan_type": rec["loan_type"],
                    "channel": rec["channel"], "question": rec["question"],
                    "answer": ans, "run_id": run_id, "shard_id": shard_id,
                    "year": int(y), "month": int(m), "day": int(d),
                }
                # Idempotent upsert: same doc_id + same values on retry.
                table.put_item(Item=row)
                manifest_lines.append(json.dumps(row))
                written += 1
    s3.put_object(Bucket=BUCKET, Key=f"manifests/{run_id}/{shard_id}.jsonl",
                  Body="\n".join(manifest_lines).encode(), ContentType="application/jsonl")
    s3.put_object(Bucket=BUCKET, Key=marker,
                  Body=json.dumps({"shard_id": shard_id, "files": written}).encode(),
                  ContentType="application/json")
    print(f"Shard {shard_id} done: {written} files, {skipped} duplicate(s) skipped.")
    return written


def main() -> int:
    print("Worker started, polling SQS…", flush=True)
    while True:
        resp = sqs.receive_message(
            QueueUrl=QUEUE_URL, MaxNumberOfMessages=1,
            WaitTimeSeconds=20, VisibilityTimeout=3600)
        for m in resp.get("Messages", []):
            body = json.loads(m["Body"])
            print(f"Processing shard {body.get('shard_id')}", flush=True)
            try:
                process_shard(body)
            except Exception as exc:  # noqa: BLE001 — leave message for redrive/DLQ
                print(f"Shard {body.get('shard_id')} FAILED: {exc}", flush=True)
                time.sleep(5)
                continue
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=m["ReceiptHandle"])
            print(f"Shard {body.get('shard_id')} acknowledged.", flush=True)
        # In AWS Batch, exit when the queue is empty for a while instead of looping forever.
        # Keep it simple here: one idle poll (20s) with no messages ends the job.
        if not resp.get("Messages"):
            print("Queue empty, worker exiting.", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
