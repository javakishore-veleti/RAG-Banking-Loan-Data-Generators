"""L4 — stores. One index per indexing layer (see README § Indexes):

  IDX-1 documents        RDS table `documents` (+ OpenSearch `loan-documents`)
  IDX-2 chunks           RDS table `chunks` (metadata-filterable)
  IDX-3 vectors          pgvector table `chunk_embeddings_<model slug>`
                         with an HNSW index, one table per embedding model
  IDX-4 keyword (BM25)   OpenSearch index `loan-chunks-bm25` — OPTIONAL,
                         only when OPENSEARCH_ENABLED=1 / endpoint is set

pgvector is the source of truth. OpenSearch is dual-written best-effort:
if it fails, the chunk row is still stored with opensearch_synced=false
and a later re-run of the same shard retries the unsynced rows — the
vector index is never held hostage by the optional keyword index.

Schema is created idempotently (CREATE EXTENSION / CREATE TABLE IF NOT
EXISTS) by init_schema(), which the worker runs once per shard before
writing. Connection details come from env: DB_HOST, DB_NAME, DB_USER,
DB_PASSWORD (or DB_SECRET_ARN for Secrets Manager — see worker.py).
"""

import json
import os

import psycopg
from psycopg.rows import dict_row

from indexer.embedding_config import model_slug

DB_HOST = os.environ.get("DB_HOST", "")
DB_NAME = os.environ.get("DB_NAME", "ragindex")
DB_USER = os.environ.get("DB_USER", "ragindex")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
OPENSEARCH_ENABLED = os.environ.get("OPENSEARCH_ENABLED", "0") == "1"


def embeddings_table(model_id):
    return f"chunk_embeddings_{model_slug(model_id)}"


def connect():
    return psycopg.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER,
                           password=DB_PASSWORD, autocommit=True,
                           row_factory=dict_row)


def init_schema(conn, *, model_id, dims):
    """Create extension, tables and indexes if missing. Safe to re-run."""
    table = embeddings_table(model_id)
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY, loan_id TEXT, loan_type TEXT,
                format TEXT, year INT, policy_version TEXT,
                latest BOOLEAN NOT NULL DEFAULT TRUE,
                source_s3_key TEXT, indexed_at TIMESTAMPTZ)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY, chunk_index INT NOT NULL,
                text TEXT NOT NULL, doc_id TEXT NOT NULL REFERENCES documents(doc_id),
                loan_id TEXT, loan_type TEXT, format TEXT, year INT,
                policy_version TEXT, latest BOOLEAN NOT NULL DEFAULT TRUE,
                page_hint TEXT, source_s3_key TEXT,
                embedding_model TEXT NOT NULL, indexed_at TIMESTAMPTZ,
                opensearch_synced BOOLEAN NOT NULL DEFAULT FALSE)
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_meta "
                    "ON chunks(loan_type, year, latest)")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id),
                embedding vector({dims}) NOT NULL)
        """)
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_hnsw "
                    f"ON {table} USING hnsw (embedding vector_cosine_ops)")


def upsert_document(conn, doc):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO documents
                (doc_id, loan_id, loan_type, format, year, policy_version,
                 latest, source_s3_key, indexed_at)
            VALUES (%(doc_id)s, %(loan_id)s, %(loan_type)s, %(format)s,
                    %(year)s, %(policy_version)s, %(latest)s,
                    %(source_s3_key)s, %(indexed_at)s)
            ON CONFLICT (doc_id) DO UPDATE SET
                latest = EXCLUDED.latest, indexed_at = EXCLUDED.indexed_at
        """, doc)


def upsert_chunks(conn, chunks, vectors, *, model_id, opensearch_synced=False):
    """Store chunk rows + their vectors. Idempotent: same chunk_id (same
    doc + chunk index + model) upserts the same row. Returns row count."""
    table = embeddings_table(model_id)
    with conn.cursor() as cur:
        for chunk, vector in zip(chunks, vectors):
            cur.execute("""
                INSERT INTO chunks
                    (chunk_id, chunk_index, text, doc_id, loan_id, loan_type,
                     format, year, policy_version, latest, page_hint,
                     source_s3_key, embedding_model, indexed_at, opensearch_synced)
                VALUES (%(chunk_id)s, %(chunk_index)s, %(text)s, %(doc_id)s,
                        %(loan_id)s, %(loan_type)s, %(format)s, %(year)s,
                        %(policy_version)s, %(latest)s, %(page_hint)s,
                        %(source_s3_key)s, %(embedding_model)s, %(indexed_at)s,
                        %(opensearch_synced)s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    text = EXCLUDED.text, indexed_at = EXCLUDED.indexed_at,
                    opensearch_synced = EXCLUDED.opensearch_synced
            """, {**chunk, "opensearch_synced": opensearch_synced})
            cur.execute(
                f"INSERT INTO {table} (chunk_id, embedding) VALUES (%s, %s) "
                f"ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                (chunk["chunk_id"], vector))
    return len(chunks)


def drop_all_index_tables(conn):
    """Drop every index table (documents, chunks, chunk_embeddings_*).
    Used by INDEX_MODE=truncate (aws-index-009). Idempotent."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND (tablename IN ('documents', 'chunks')
                 OR tablename LIKE 'chunk_embeddings\\_%')
        """)
        for row in cur.fetchall():
            cur.execute(f'DROP TABLE IF EXISTS "{row["tablename"]}" CASCADE')
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return [row["tablename"] for row in cur.fetchall()]


def vector_search(conn, query_vector, *, model_id, top_k=4, filters=None):
    """Cosine-similarity search with optional metadata filters
    ({'loan_type': 'home', 'latest': True, ...}). Retrieval-layer read."""
    table = embeddings_table(model_id)
    where, filter_values = "", []
    if filters:
        clauses = []
        for key, value in filters.items():
            clauses.append(f"c.{key} = %s")
            filter_values.append(value)
        where = "WHERE " + " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT c.*, e.embedding <=> %s AS distance
            FROM chunks c JOIN {table} e ON e.chunk_id = c.chunk_id
            {where} ORDER BY distance ASC LIMIT %s
        """, [query_vector, *filter_values, top_k])
        return cur.fetchall()


class OpenSearchStore:
    """Optional BM25 keyword index. Best-effort: failures are reported
    to the caller, never fatal to the pgvector write."""

    def __init__(self, endpoint=None, client=None):
        self.endpoint = endpoint or OPENSEARCH_ENDPOINT
        self.enabled = bool(self.endpoint) and OPENSEARCH_ENABLED
        self._client = client

    def _get_client(self):
        if self._client is None:
            from opensearchpy import OpenSearch
            self._client = OpenSearch(hosts=[{"host": self.endpoint, "port": 443}],
                                      http_compress=True, use_ssl=True,
                                      verify_certs=True, ssl_show_warn=False)
        return self._client

    def ensure_index(self, index="loan-chunks-bm25"):
        client = self._get_client()
        if not client.indices.exists(index=index):
            client.indices.create(index=index, body={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {"properties": {
                    "text": {"type": "text"},
                    "chunk_id": {"type": "keyword"},
                    "doc_id": {"type": "keyword"},
                    "loan_type": {"type": "keyword"},
                    "year": {"type": "integer"},
                    "latest": {"type": "boolean"},
                    "policy_version": {"type": "keyword"}}}})

    def index_chunks(self, chunks, index="loan-chunks-bm25"):
        """Bulk-index chunk texts. Returns True on success, False on error."""
        if not self.enabled:
            return False
        try:
            client = self._get_client()
            self.ensure_index(index)
            body = []
            for chunk in chunks:
                body.append({"index": {"_index": index, "_id": chunk["chunk_id"]}})
                body.append({k: chunk[k] for k in
                             ("text", "chunk_id", "doc_id", "loan_type",
                              "year", "latest", "policy_version")})
            client.bulk(body=body)
            return True
        except Exception:  # noqa: BLE001 — best-effort by design
            return False
