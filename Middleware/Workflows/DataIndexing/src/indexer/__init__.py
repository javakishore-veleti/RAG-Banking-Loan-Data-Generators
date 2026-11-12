"""DataIndexing — index the generated loan corpus for RAG retrieval.

Layers (see README.md and the video "Build Production-Ready Advanced
RAG From Scratch"):
  L0 load     loader.py     — read a source doc (pdf/docx/xlsx/csv/txt/png)
  L1 chunk    chunker.py    — recursive split, 500 tokens / 100 overlap
  L2 enrich   enricher.py   — metadata: loan, year, latest flag, policy version
  L3 embed    embedder.py   — Amazon Bedrock embeddings, per-format model
                              with default fallback + model failover
  L4 store    stores.py     — pgvector (vector index) + OpenSearch (BM25,
                              optional) + DynamoDB index manifest

planner.py is the Step Functions Lambda; worker.py is the Batch worker.
pipeline.py wires L0–L4 together for one document, idempotently.
"""
