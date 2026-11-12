"""Pipeline — wire L0–L4 together for one document, idempotently.

index_document(doc, data, ...):
  L0 loader.extract_text      -> plain text ('' for PNG)
  fallback: manifest description text when extraction yields nothing
  L1 chunker.split_text       -> overlapping chunks
  L2 enricher.enrich_chunks   -> metadata (latest flag, policy version, ids)
  L3 embedder.embed_batch     -> vectors (model failover recorded)
  L4 stores: pgvector upsert  -> source of truth, always
     stores: OpenSearch index -> best-effort; unsynced rows are retried
            on the next run of the same shard
     DynamoDB index_manifest  -> per-chunk status (indexed/failed, model)

Re-running the same document with the same model upserts the same
chunk ids — safe to replay a shard after a failure. A different model
creates different chunk ids, so re-indexing with another model adds a
new vector table instead of clobbering the old one.
"""

import json
import os

import boto3

from indexer.embedding_config import resolve_model
from indexer.loader import extract_text
from indexer.chunker import split_text
from indexer.enricher import enrich_chunks
from indexer.embedder import BedrockEmbedder
from indexer.stores import (connect, init_schema, upsert_document, upsert_chunks,
                    OpenSearchStore)

TABLE = os.environ.get("INDEX_MANIFEST_TABLE", "")
REGION = os.environ.get("AWS_REGION", "ap-south-1")


def _load_manifest_descriptions(bucket, manifest_key, s3):
    """{doc_id: description} from a manifest.jsonl in S3 (ground truth)."""
    out = {}
    try:
        obj = s3.get_object(Bucket=bucket, Key=manifest_key)
        for line in obj["Body"].read().decode("utf-8").splitlines():
            row = json.loads(line)
            desc = row.get("description") or ""
            if row.get("doc_id") and desc:
                out[row["doc_id"]] = desc
    except Exception:  # noqa: BLE001 — manifest is a fallback, not required
        pass
    return out


def index_document(doc, data, *, embedder=None, conn=None, opensearch=None,
                   manifest_descriptions=None, embedding_model=None,
                   config=None, dynamodb=None):
    """Index one document. Returns a summary dict (counts + model used).
    Raises on failure — the caller (worker) lets SQS redrive the shard."""
    fmt = doc["format"]
    text = extract_text(fmt, data)
    if not text and manifest_descriptions:
        text = manifest_descriptions.get(doc["doc_id"], "")
    if not text:
        raise ValueError(f"no indexable text for {doc['doc_id']} ({fmt})")

    model_id, model_source = resolve_model(fmt, explicit=embedding_model,
                                           config=config)
    embedder = embedder or BedrockEmbedder()
    chunks = split_text(text)
    enriched = enrich_chunks(doc, chunks, embedding_model=model_id)
    vectors, model_used = embedder.embed_batch(model_id, [c["text"] for c in enriched])
    # Failover may have changed the model: chunk ids embed the model slug,
    # so re-enrich with the model actually used before storing.
    if model_used != model_id:
        enriched = enrich_chunks(doc, chunks, embedding_model=model_used)

    conn = conn or connect()
    dims = embedder.probe_dimensions(model_used)
    init_schema(conn, model_id=model_used, dims=dims)
    upsert_document(conn, {
        "doc_id": doc["doc_id"], "loan_id": doc.get("loan_id"),
        "loan_type": doc.get("loan_type"), "format": fmt,
        "year": doc.get("year"), "policy_version": doc.get("policy_version"),
        "latest": bool(doc.get("latest", True)),
        "source_s3_key": doc.get("source_s3_key"),
        "indexed_at": enriched[0]["indexed_at"] if enriched else None,
    })

    opensearch = opensearch if opensearch is not None else OpenSearchStore()
    synced = False
    if opensearch.enabled:
        synced = opensearch.index_chunks(enriched)
    upsert_chunks(conn, enriched, vectors, model_id=model_used,
                  opensearch_synced=synced)

    _record_manifest(doc, enriched, model_used, dynamodb, synced=synced)
    return {"doc_id": doc["doc_id"], "chunks": len(enriched),
            "model_requested": model_id, "model_used": model_used,
            "model_source": model_source, "opensearch_synced": synced}


def _record_manifest(doc, chunks, model_used, dynamodb, *, synced=False):
    if not TABLE:
        return
    table = (dynamodb or boto3.resource("dynamodb", region_name=REGION)).Table(TABLE)
    with table.batch_writer() as batch:
        for chunk in chunks:
            batch.put_item(Item={
                "chunk_id": chunk["chunk_id"], "doc_id": doc["doc_id"],
                "loan_id": doc.get("loan_id"), "format": doc.get("format"),
                "year": doc.get("year"), "embedding_model": model_used,
                "status": "indexed", "indexed_at": chunk["indexed_at"],
                "opensearch_synced": synced,
            })
