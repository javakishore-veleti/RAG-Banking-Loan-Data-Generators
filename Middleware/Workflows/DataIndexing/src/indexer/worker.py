"""Batch worker — one shard = one SQS message.

Message body (JSON):
  {"shard_id": "shard-0000", "keys": ["raw/pdf/year=2024/...", ...],
   "format": "pdf", "year": 2024, "run_id": "2024-pdf-001",
   "embedding_model": "", "bucket": "<corpus bucket>"}

Behaviour:
  - Polls SQS (long poll, one message at a time — a shard is big).
  - For each key: download the doc, load the manifest row for it
    (loan_id, policy_version, latest flag) from manifest.jsonl, run
    pipeline.index_document (load -> chunk -> enrich -> Bedrock embed
    -> pgvector upsert -> OpenSearch best-effort -> DynamoDB manifest).
  - Writes a completion marker:
      s3://<BUCKET>/index-markers/<run_id>/<shard_id>.done
    (Step Functions checks markers; a shard with a marker is skipped
    on replay.)
  - Deletes the SQS message ONLY after the whole shard succeeds.
    Any exception -> message stays visible, SQS redrives it (3x),
    then the DLQ. Bedrock throttling is retried inside the embedder;
    model failover is recorded in the chunk metadata.
  - DB credentials: read the master secret from Secrets Manager
    (DB_SECRET_ARN) on start; the password is never in env or code.

Env: CORPUS_BUCKET, INDEX_MANIFEST_TABLE, QUEUE_URL, AWS_REGION,
     DB_HOST, DB_NAME, DB_USER, DB_SECRET_ARN,
     OPENSEARCH_ENDPOINT, OPENSEARCH_ENABLED
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3
from botocore.config import Config

from indexer import pipeline as pipeline_mod  # noqa: E402
from indexer.stores import OpenSearchStore  # noqa: E402

BUCKET = os.environ["CORPUS_BUCKET"]
TABLE = os.environ.get("INDEX_MANIFEST_TABLE", "")
QUEUE_URL = os.environ["QUEUE_URL"]
REGION = os.environ.get("AWS_REGION", "ap-south-1")
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN", "")

RETRY = Config(retries={"max_attempts": 5, "mode": "adaptive"})


def load_db_password():
    """Fetch the RDS master password from Secrets Manager (once)."""
    if not DB_SECRET_ARN:
        return os.environ.get("DB_PASSWORD", "")
    sm = boto3.client("secretsmanager", region_name=REGION)
    secret = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    return json.loads(secret["SecretString"])["password"]


def load_manifest(s3, bucket, fmt, year):
    """{doc_id: manifest row} for one format+year, from manifest.jsonl."""
    out = {}
    try:
        obj = s3.get_object(Bucket=bucket,
                            Key=f"manifests/{fmt}-{year}.jsonl")
        for line in obj["Body"].read().decode("utf-8").splitlines():
            row = json.loads(line)
            out[row["doc_id"]] = row
    except Exception:  # noqa: BLE001 — manifest may not exist yet
        pass
    return out


def doc_from_key(key, fmt, manifest_row):
    """Doc dict for the pipeline, from an S3 key + its manifest row."""
    doc_id = Path(key).stem
    row = manifest_row or {}
    return {
        "doc_id": doc_id,
        "loan_id": row.get("loan_id"),
        "loan_type": row.get("loan_type"),
        "format": fmt,
        "year": row.get("year"),
        "policy_version": row.get("policy_version"),
        "latest": bool(row.get("latest", True)),
        "source_s3_key": key,
    }


def process_shard(msg, *, s3, sqs, conn, embedder, opensearch, dynamodb):
    body = json.loads(msg["Body"])
    fmt, year, run_id = body["format"], body["year"], body["run_id"]
    manifest = load_manifest(s3, BUCKET, fmt, year)
    descriptions = {k: v.get("description", "") for k, v in manifest.items()}
    indexed, failed = 0, []
    for key in body["keys"]:
        doc = doc_from_key(key, fmt, manifest.get(Path(key).stem))
        data = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        try:
            pipeline_mod.index_document(
                doc, data, embedder=embedder, conn=conn,
                opensearch=opensearch, dynamodb=dynamodb,
                manifest_descriptions=descriptions,
                embedding_model=body.get("embedding_model") or None)
            indexed += 1
        except Exception as exc:  # noqa: BLE001 — one bad doc must not
            failed.append({"key": key, "error": str(exc)})  # kill the shard
    marker = f"index-markers/{run_id}/{body['shard_id']}.done"
    s3.put_object(Bucket=BUCKET, Key=marker,
                  Body=json.dumps({"shard_id": body["shard_id"],
                                   "indexed": indexed, "failed": failed}).encode())
    if failed:
        raise RuntimeError(f"shard {body['shard_id']}: {len(failed)} docs failed: "
                           f"{failed[0]['key']}: {failed[0]['error']}")
    sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
    return {"shard_id": body["shard_id"], "indexed": indexed}


def main():
    import indexer.stores as stores
    if os.environ.get("INDEX_MODE") == "truncate":
        # One-off truncate run (aws-index-009 submits the indexer image
        # with INDEX_MODE=truncate: the job runs inside the VPC, so it
        # can reach the private RDS instance — a GitHub runner cannot).
        os.environ["DB_PASSWORD"] = load_db_password()
        conn = stores.connect()
        remaining = stores.drop_all_index_tables(conn)
        print("index tables dropped; remaining public tables:", remaining, flush=True)
        return
    os.environ["DB_PASSWORD"] = load_db_password()
    s3 = boto3.client("s3", region_name=REGION, config=RETRY)
    sqs = boto3.client("sqs", region_name=REGION, config=RETRY)
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    conn = stores.connect()
    embedder = pipeline_mod.BedrockEmbedder()
    opensearch = OpenSearchStore()
    print("indexer worker started, polling", QUEUE_URL, flush=True)
    while True:
        resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=1,
                                   WaitTimeSeconds=20, VisibilityTimeout=900)
        for msg in resp.get("Messages", []):
            print("shard:", json.loads(msg["Body"])["shard_id"], flush=True)
            process_shard(msg, s3=s3, sqs=sqs, conn=conn,
                          embedder=embedder, opensearch=opensearch,
                          dynamodb=dynamodb)
            print("shard done", flush=True)
        if not resp.get("Messages"):
            print("queue empty, exiting", flush=True)
            return


if __name__ == "__main__":
    main()
