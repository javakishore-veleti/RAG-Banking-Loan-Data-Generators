"""L2 — chunk enrichment: the metadata that makes retrieval work.

Every chunk carries the fields the retrieval layer filters on (this is
the video's "latest=true/false" pattern, extended to banking loans):
  doc_id, loan_id, loan_type, format, year, policy_version, latest,
  chunk_index, page_hint, source_s3_key, embedding_model, indexed_at.

`latest` is the version flag: when a loan has documents from several
years (or a policy has several versions), only the newest is latest.
The policy_version comes from the Datagen manifest record for the
document; when the manifest has none, it is None (not guessed).

Chunk ids are deterministic — sha1(doc_id + chunk_index + embedding
model slug) — so re-indexing the same document with the same model
upserts the same rows instead of duplicating them. A different model
gets different chunk ids, which is how one document can live in
several vector tables (one per model) without collisions.
"""

import hashlib
import itertools
from datetime import datetime, timezone

from indexer.embedding_config import model_slug


def enrich_chunks(doc, chunks, *, embedding_model, indexed_at=None):
    """Attach metadata to chunk texts.

    `doc` is a dict with at least: doc_id, loan_id, loan_type, format,
    year, source_s3_key. Optional: policy_version (str), latest (bool),
    page_hint. Returns a list of dicts {chunk_id, chunk_index, text, ...}.
    """
    indexed_at = indexed_at or datetime.now(timezone.utc).isoformat()
    slug = model_slug(embedding_model)
    out = []
    for i, text in enumerate(chunks):
        chunk_id = hashlib.sha1(
            f"{doc['doc_id']}:{i}:{slug}".encode("utf-8")
        ).hexdigest()
        out.append({
            "chunk_id": chunk_id,
            "chunk_index": i,
            "text": text,
            "doc_id": doc["doc_id"],
            "loan_id": doc.get("loan_id"),
            "loan_type": doc.get("loan_type"),
            "format": doc.get("format"),
            "year": doc.get("year"),
            "policy_version": doc.get("policy_version"),
            "latest": bool(doc.get("latest", True)),
            "page_hint": doc.get("page_hint"),
            "source_s3_key": doc.get("source_s3_key"),
            "embedding_model": embedding_model,
            "indexed_at": indexed_at,
        })
    return out


def latest_flag_for(doc_year, latest_year):
    """True when a document's year is the newest year seen for its loan."""
    if latest_year is None or doc_year is None:
        return True
    return doc_year >= latest_year


def group_latest_flags(docs):
    """Given docs (dicts with loan_id + year), return {doc_id: latest}.
    Latest = the max year per loan_id; ties (same year) are all latest."""
    by_loan = {}
    for doc in docs:
        by_loan.setdefault(doc.get("loan_id"), []).append(doc)
    flags = {}
    for loan_id, group in by_loan.items():
        years = [d.get("year") for d in group if d.get("year") is not None]
        newest = max(years) if years else None
        for doc in group:
            flags[doc["doc_id"]] = latest_flag_for(doc.get("year"), newest)
    return flags
