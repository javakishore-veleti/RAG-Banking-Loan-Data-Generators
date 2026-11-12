# GitHub Issues Plan — Data Indexing Only

> Scope: data indexing only. No retrieval, reranking, agents, or UI.
> Those are the API-Services phase, with their own plan when it starts.
>
> **Totals: 2 milestones, 5 epics, 13 features, 35 stories = 55 issues**
> (milestones are GitHub milestones, not issues; epics/features/stories
> are all GitHub issues, linked parent → child).
>
> **How to use this in GitHub:**
> 1. Create the 2 milestones (M006–M007) in the repo.
> 2. Create the 5 epic issues, label `epic`, assign each to its milestone.
> 3. Create the 13 feature issues, label `feature`, link to their epic.
> 4. Create the 35 story issues, label `story`, link to their feature.
> 5. Work milestone by milestone. Do not start M007 (scale) before
>    M006 is done — the cloud pipeline amplifies whatever the local
>    indexer does, good or bad.
>
> **Labels to create:** `epic`, `feature`, `story`, plus topical labels
> per issue — `aws`, `s3`, `dynamodb`, `sqs`, `batch`, `lambda`,
> `step-functions`, `cloudformation`, `ecr`, `cloudwatch`,
> `index-wf`, `github-actions`, `infra-setup`, `infra-destroy`,
> `data-delete`, `data-indexing`, `chunking`, `metadata`, `bedrock`,
> `embeddings`, `pgvector`, `rds`, `opensearch`, `hybrid-search`,
> `testing`, `docs`, `observability`. Every issue gets its type
> label *and* its topical labels. The mapping lives in
> `scripts/create_issues.py` (`EPIC_LABELS` / `FEATURE_LABELS`);
> stories inherit their feature's labels.
>
> **Status as work progresses:** issues are closed as their code
> lands and is verified, via `scripts/close_index_issues.py`
> (manual workflow `Close Index Issues`). Nothing is closed without
> Kishore approving the list — closing is the status change itself.
> See `GITHUB_ISSUES.md` for the Datagen plan (127 issues).

---

## Milestones (2)

| # | Milestone | Goal | Exit criteria |
|---|---|---|---|
| M006 | Indexing Foundation & Pipeline | Indexer runs locally, one format, metadata + vectors land in pgvector | Local dry-run + unit tests pass; one format indexed end to end in AWS (100 docs) |
| M007 | Indexes, Quality & Hardening | All six formats indexed, retry/failover proven, teardown verified | All formats indexed for one year; DLQ empty; re-run idempotent; teardown + data deletion verified |

---

## Epics (5)

| # | Epic | Milestone | Features |
|---|---|---|---|
| E010 | Indexing core & metadata | M006 | F034–F036 |
| E011 | Embeddings & Bedrock | M006 | F037–F038 |
| E012 | Vector & keyword indexes | M006 | F039–F040 |
| E013 | Execution & orchestration | M007 | F041–F044 |
| E014 | Quality, observability & release | M007 | F045–F046 |

---

## Features & Stories (13 features, 35 stories)

### E010 — Indexing core & metadata (M006)

**F034 — Document loading per format**
- S086. Extract text from PDF (pypdf) and DOCX (python-docx).
- S087. Extract text from XLSX (openpyxl) and CSV rows.
- S088. TXT loads as-is; PNG falls back to the manifest ground-truth description.

**F035 — Chunking 500/100**
- S089. Recursive splitter, 500 tokens / 100 overlap (2000/400 chars), separators "\n\n, \n, ". ", " ".
- S090. Overlap preserves text with no loss; short documents yield one chunk.

**F036 — Metadata enrichment**
- S091. Metadata schema: doc_id, loan_id, loan_type, format, year, policy_version, latest, page_hint, source_s3_key, embedding_model, indexed_at.
- S092. latest flag = newest version per loan_id (max year); policy_version recorded per chunk.
- S093. Deterministic chunk ids: sha1(doc_id:chunk_index:model_slug); different model → different id.

### E011 — Embeddings & Bedrock (M006)

**F037 — Bedrock embedder**
- S094. Invoke Bedrock embedding model per chunk batch; record model actually used.
- S095. Throttling retries with exponential backoff + jitter (5 attempts).
- S096. Fail over to the default model once on AccessDenied/Validation/NotFound.

**F038 — Embedding model config**
- S097. config/embedding_models.yaml: default_model amazon.titan-embed-text-v2:0, per-format overrides (null = default).
- S098. Resolution order: workflow input → per-format override → default.
- S099. Dimensions table for known models; probe_dimensions for unknown models.

### E012 — Vector & keyword indexes (M006)

**F039 — pgvector schema**
- S100. documents + chunks tables with metadata indexes.
- S101. One chunk_embeddings_<model slug> table per model, HNSW index (vector_cosine_ops).
- S102. vector_search with metadata filters (loan_type, year, latest).

**F040 — OpenSearch BM25 (optional)**
- S103. OpenSearch Serverless collection + index loan-chunks-bm25 behind EnableOpenSearch.
- S104. Best-effort dual-write; opensearch_synced flags unsynced rows.
- S105. Unsynced rows retried on the next run.

### E013 — Execution & orchestration (M007)

**F041 — Index planner Lambda**
- S106. List raw/<fmt>/year=YYYY/ keys from S3 and shard them (default 100 docs/shard).
- S107. FIFO SQS dedup id = run_id-shard_id; .done markers per shard.

**F042 — Batch index worker**
- S108. Poll SQS one message at a time; index a whole shard, then delete the message.
- S109. Any document failure fails the shard → SQS redrive 3x → DLQ; re-run upserts (idempotent).

**F043 — Step Functions + workflows**
- S110. AWS-Index-001 provision: indexing + orchestration stacks, reuses AWS-001 VPC by default.
- S111. AWS-Index-002 reusable + AWS-Index-003…008 per-format wrappers.
- S112. AWS-Index-009 delete index data + AWS-Index-010 destroy (typed confirmations; shared VPC untouched).

**F044 — Retry & failover**
- S113. SQS redrive 3x → DLQ, Batch retry 3x, Step Functions retries on failed shards.
- S114. Idempotent re-runs: deterministic chunk ids + .done markers; no duplicates on retry.
- S115. RDS Multi-AZ option (multi_az input, default false for learning).

### E014 — Quality, observability & release (M007)

**F045 — Testing & evaluation**
- S116. Unit tests: chunker, enricher, embedding config, retry, loader (8 tests).
- S117. Local dry-run: run_local.sh tests + L0–L2 dry-run with no AWS.
- S118. Golden-set retrieval check: index a small set, verify known answers are found (pgvector).

**F046 — Docs & release**
- S119. README §15, ARCHITECTURE §15, DESIGN §16 + decision log updated.
- S120. CI runs indexer tests + py_compile; GITHUB_ISSUES_INDEXING.md plan + create-index-issues workflow in repo.
