#!/usr/bin/env python3
"""
Planner Lambda — invoked by Step Functions at the start of a run.

Input (JSON) — one document type per run, triggered manually per format:
  {"total_per_format": 200000, "shard_size": 10000,
   "formats": ["pdf"], "year": 2024, "seed": 7,
   "run_id": "2024-pdf-001"}

Output: {"run_id": ..., "shards_enqueued": 20, "shards": [...]}

Behaviour:
  - Computes shards: ceil(total / shard_size) for this format+year.
    200k/year at 10k/shard = 20 shards. 10 years = 200 shards per format.
  - Sends one SQS message per shard (batch send, 10 at a time).
  - Shard messages are idempotent: same run_id + shard_id + start always
    generates the same files (deterministic seed + start offset + year).
"""
import json
import math
import os
import uuid

import boto3

QUEUE_URL = os.environ["QUEUE_URL"]
sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "ap-south-1"))


def handler(event, _context):
    total = int(event.get("total_per_format", 1000))
    shard_size = int(event.get("shard_size", 10000))
    formats = event.get("formats", ["pdf"])
    year = event.get("year")
    seed = int(event.get("seed", 7))
    run_id = event.get("run_id") or f"run-{uuid.uuid4().hex[:8]}"

    n_shards = math.ceil(total / shard_size)
    shards = []
    for n in range(n_shards):
        start = n * shard_size
        count = min(shard_size, total - start)
        shards.append({
            "shard_id": f"shard-{n:04d}", "start": start, "count": count,
            "formats": formats, "year": year, "seed": seed, "run_id": run_id,
        })

    # SQS SendMessageBatch, 10 entries at a time.
    for i in range(0, len(shards), 10):
        batch = shards[i:i + 10]
        sqs.send_message_batch(
            QueueUrl=QUEUE_URL,
            Entries=[{
                "Id": s["shard_id"],
                "MessageBody": json.dumps(s),
                # Deduplication: same run + shard re-planned = same dedup id.
                "MessageDeduplicationId": f"{run_id}-{s['shard_id']}",
                "MessageGroupId": run_id,
            } for s in batch],
        )
    return {"run_id": run_id, "formats": formats, "year": year,
            "shards_enqueued": len(shards), "shards": shards}
