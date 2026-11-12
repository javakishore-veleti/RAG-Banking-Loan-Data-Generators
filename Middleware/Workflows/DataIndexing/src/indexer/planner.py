"""Planner Lambda — one Step Functions run = one format + year.

Input (from the state machine):
  {"bucket": ..., "format": "pdf", "year": 2024, "count": 1000,
   "shard_size": 100, "seed": 7, "run_id": "2024-pdf-001",
   "embedding_model": "" }

The planner lists the source docs for that format+year in S3
(raw/<format>/year=YYYY/...), splits the key list into shards of
`shard_size` documents, and enqueues one SQS FIFO message per shard.
It does NOT load documents — the Batch workers do that. Keep the
planner fast: listing + enqueueing only, well inside Lambda limits.

Output: {"shards": <n>, "documents": <n>, "run_id": ...}
"""

import json
import os

import boto3

QUEUE_URL = os.environ.get("QUEUE_URL", "")
REGION = os.environ.get("AWS_REGION", "ap-south-1")


def list_documents(s3, bucket, fmt, year):
    """S3 keys for one format + year, sorted for determinism."""
    prefix = f"raw/{fmt}/year={year}/"
    keys, token = [], None
    while True:
        args = {"Bucket": bucket, "Prefix": prefix}
        if token:
            args["ContinuationToken"] = token
        page = s3.list_objects_v2(**args)
        keys += [o["Key"] for o in page.get("Contents", [])]
        if not page.get("IsTruncated"):
            break
        token = page["NextContinuationToken"]
    return sorted(keys)


def plan_shards(keys, shard_size):
    """Split a key list into shards: [{'shard_id', 'keys', ...}]."""
    return [{"shard_id": f"shard-{i:04d}",
             "keys": keys[i * shard_size:(i + 1) * shard_size]}
            for i in range((len(keys) + shard_size - 1) // shard_size)]


def lambda_handler(event, _context=None):
    s3 = boto3.client("s3", region_name=REGION)
    sqs = boto3.client("sqs", region_name=REGION)
    bucket = event["bucket"]
    fmt, year = event["format"], event["year"]
    shard_size = int(event.get("shard_size", 100))
    run_id = event["run_id"]

    keys = list_documents(s3, bucket, fmt, year)
    shards = plan_shards(keys, shard_size)
    for shard in shards:
        body = {"shard_id": shard["shard_id"], "keys": shard["keys"],
                "format": fmt, "year": year, "run_id": run_id,
                "embedding_model": event.get("embedding_model", ""),
                "bucket": bucket}
        # FIFO dedup: same run + shard enqueued twice = one message.
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(body),
                         MessageGroupId=run_id,
                         MessageDeduplicationId=f"{run_id}-{shard['shard_id']}")
    return {"shards": len(shards), "documents": len(keys), "run_id": run_id}
