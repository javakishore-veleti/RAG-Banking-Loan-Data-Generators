# Middleware

Server-side apps. Each app under here is self-contained: its own
source, its own Dockerfile, its own deployments. Apps never share
a Docker image.

- `Workflows/Datagen/` — synthetic banking-loan data generation
  (ETL).
- `Workflows/DataIndexing/` — index the generated corpus for RAG
  retrieval: load → chunk → enrich (metadata) → Bedrock embed →
  pgVector (+ optional OpenSearch BM25). See its README.
- `API-Services/` — future: loan / RAG query APIs (LangChain agent
  and AWS Strands agent, two endpoints). Not built yet.
