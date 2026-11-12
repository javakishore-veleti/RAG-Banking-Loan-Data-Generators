# Workflows

Background / batch apps (no HTTP traffic of their own).

- `Datagen/` — synthetic loan-data generation. See its README.
- `DataIndexing/` — index the generated corpus for RAG retrieval:
  load → chunk → enrich → Bedrock embed → pgVector (+ optional
  OpenSearch). See its README.
