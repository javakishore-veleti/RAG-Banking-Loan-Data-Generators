# DataIndexing deployments

## Docker image

- **Built by:** the `aws-index-001-provision.yml` workflow (root
  `.github/workflows/`), from this folder as build context:
  `docker build -f Middleware/Workflows/DataIndexing/Dockerfile Middleware/Workflows/DataIndexing`
- **Image:** `<project>-indexer` (e.g. `rag-corpus-indexer`), pushed to
  ECR as `<account>.dkr.ecr.<region>.amazonaws.com/<project>-indexer:latest`
- **Entrypoint:** `src/indexer/worker.py` — polls the indexing SQS FIFO
  queue until empty. Never shares Datagen's `<project>-worker` image.

## AWS resources (provisioned by AWS-Index-001)

Deploy order: storage (RDS pgvector + SQS + DynamoDB) → compute
(ECR + Batch) → orchestration (planner Lambda + Step Functions).
The VPC is reused from AWS-001 (`$PROJECT-vpc` stack / secrets /
`create-new`); this app does not create its own VPC.

- **RDS PostgreSQL** (pgvector extension) — `documents`, `chunks`,
  `chunk_embeddings_<model>` tables. Master password generated into
  Secrets Manager; the worker reads it at start.
- **OpenSearch Serverless** (optional, `EnableOpenSearch=true`) —
  `loan-chunks-bm25` collection for hybrid search.
- **SQS FIFO** `<project>-index-shards.fifo` + DLQ (3 redeliveries).
- **DynamoDB** `<project>-index-manifest` — per-chunk indexing status.
- **Step Functions** `<project>-index-run` — CustomerCase-PlanShards →
  CustomerCase-SubmitBatchWorkers.

## Teardown (end of life, in order)

1. `aws-index-009-delete-index-data.yml` — empties the vector and
   chunk tables and the index manifest.
2. `aws-index-010-destroy.yml` — deletes the stacks in reverse order
   (orchestration → compute → storage). The shared VPC stack is
   deleted by Datagen's AWS-010, not here.
