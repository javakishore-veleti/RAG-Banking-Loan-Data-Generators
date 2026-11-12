# DataIndexing — index the loan corpus for RAG retrieval

Second Workflow app in `Middleware/Workflows/` (sibling of `Datagen/`).
Datagen **generates** the documents; this app **indexes** them so the
future API-Services agents can retrieve answers from them. Own Docker
image (`<project>-indexer`), own CloudFormation stacks, own GitHub
Actions (`AWS-Index-001` … `AWS-Index-010`).

## The layers (from the video "Build Production-Ready Advanced RAG From Scratch")

| Layer | Step | Code | What it does |
|---|---|---|---|
| L0 | Load | `src/indexer/loader.py` | Read a source doc (pdf/docx/xlsx/csv/txt/png) into text. PNG has no text layer — falls back to the manifest ground-truth description. |
| L1 | Chunk | `src/indexer/chunker.py` | Recursive split, 500 tokens / 100 overlap (video settings). |
| L2 | Enrich | `src/indexer/enricher.py` | Metadata per chunk: loan, year, `latest` flag, policy version, doc id, source S3 key. Deterministic chunk ids. |
| L3 | Embed | `src/indexer/embedder.py` | Amazon Bedrock embeddings. Model per document type from `config/embedding_models.yaml`, default `amazon.titan-embed-text-v2:0`. Retries with backoff; fails over to the default model if the configured one is rejected, and records the model actually used. |
| L4 | Store | `src/indexer/stores.py` | pgvector (source of truth) + OpenSearch BM25 (optional, best-effort) + DynamoDB index manifest. |

## The indexes (one per layer)

| Index | Where | Content |
|---|---|---|
| IDX-1 `documents` | RDS table `documents` (+ OpenSearch `loan-documents`) | One row per source document + metadata |
| IDX-2 `chunks` | RDS table `chunks` | One row per chunk + full metadata (filterable: loan_type, year, latest) |
| IDX-3 vectors | pgvector `chunk_embeddings_<model slug>` | One vector table per embedding model, HNSW index (cosine). A document indexed with two models lives in two tables. |
| IDX-4 keyword | OpenSearch `loan-chunks-bm25` | BM25 text index for hybrid search. **Optional** — off unless `EnableOpenSearch=true`. |

## Retry & failover

- **Bedrock throttling:** exponential backoff + jitter, 5 attempts.
- **Model failover:** configured model rejected (not enabled / access
  denied) → fall back to the default model once, record it in metadata.
- **Shard retries:** SQS redelivery 3x → DLQ; Batch job retry 3x;
  Step Functions retries the failed shard with backoff.
- **Idempotency:** chunk ids are `sha1(doc_id:chunk_index:model)` — a
  re-run upserts the same rows. `.done` markers per shard in S3.
- **OpenSearch is never on the critical path:** pgvector writes first;
  OpenSearch failures leave `opensearch_synced=false` and the next run
  of the same shard retries the unsynced rows.

## Embedding models

When you run AWS-Index-003…008, the Run workflow dialog shows an
**Embedding model** dropdown: `default`, `amazon.titan-embed-text-v2:0`,
`amazon.titan-embed-text-v1:0`, `cohere.embed-english-v3`,
`cohere.embed-multilingual-v3`. Pick one to override for that run
only, or leave `default` — it resolves through
`config/embedding_models.yaml` (per-format override, else
`default_model`), so choosing a model never needs a file edit.

To change what `default` means, edit `config/embedding_models.yaml`:
set `default_model`, or add a per-format override
(`pdf: cohere.embed-english-v3`). `null` means "use the default". If
you reference a model id the config doesn't know the dimensions of,
the embedder probes Bedrock once and measures the vector length.

Bedrock model access must be enabled in the AWS console (one time)
before the first run — the embedder fails over to the default model
if the configured one is not enabled, and says so in the chunk
metadata (check `embedding_model` in the `chunks` table).

## Run it (AWS)

1. Set the 5 GitHub secrets (same as Datagen — no new secrets needed):
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`,
   `AWS_ACCOUNT_ID`, `PROJECT`.
2. **AWS-Index-001 Provision** — deploys RDS PostgreSQL (pgvector),
   SQS FIFO + DLQ, DynamoDB index manifest, ECR, Batch, Step
   Functions. Reuses the VPC from AWS-001 (`$PROJECT-vpc` stack,
   secrets, or `create-new` — same `vpc_mode` choice). Set
   `opensearch_enabled=true` only if you want the BM25 index too.
3. **AWS-Index-003 … AWS-Index-008** — index one format (PDF, DOCX,
   XLSX, CSV, TXT, PNG) for one year. Start with `count` small
   (e.g. 100 docs) and check the row counts before a big run.

## Run it (local, no AWS)

```bash
bash scripts/run_local.sh        # unit tests + dry-run L0–L2
python -m pytest tests/ -q       # unit tests only (needs pytest)
```

## Teardown (end of life, in order)

1. **AWS-Index-009 Delete Index Data** — empties the vector tables
   and the index manifest (typed confirmation).
2. **AWS-Index-010 Destroy** — deletes the stacks in reverse order
   (orchestration → compute → storage). The shared `$PROJECT-vpc`
   stack is deleted by AWS-010 (Datagen), not here.

## What this is not

- **Not retrieval.** Hybrid search, self-query, decomposition,
  reranking and the answer step live in `Middleware/API-Services`
  (LangChain agent and AWS Strands agent — next phase), which reads
  these indexes. This app only builds them.
- **Not multi-modal.** PNGs are indexed from their manifest
  description text; plug an OCR engine into `loader.py` later if
  image text is needed.
