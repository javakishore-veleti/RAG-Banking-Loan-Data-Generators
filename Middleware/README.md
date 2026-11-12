# Middleware

Server-side apps. Each app under here is self-contained: its own
source, its own Dockerfile, its own deployments. Apps never share
a Docker image.

- `Workflows/Datagen/` — synthetic banking-loan data generation
  (ETL). The only app built so far.
- `API-Services/` — future: loan / RAG query APIs. Not built yet.
