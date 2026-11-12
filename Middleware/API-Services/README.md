# API-Services

Future. Server-side APIs that will sit next to the Datagen and
DataIndexing workflows — loan-query / RAG-answer APIs that serve
the Loan-Advisor portal.

Planned as two agents behind two different API endpoints, both
reading the indexes built by `Workflows/DataIndexing/`:

- **LangChain agent** endpoint
- **AWS Strands agent** endpoint

so the two approaches can be compared on the same corpus and the
same golden questions. Retrieval (hybrid search with RRF,
self-query metadata filtering, decomposition, cross-encoder
reranking) belongs here, not in DataIndexing.

Not built yet. When the first one is built it gets its own folder
here, with its own Dockerfile and its own deployments, exactly
like `Workflows/Datagen/`. It must not reuse Datagen's or
DataIndexing's image.
