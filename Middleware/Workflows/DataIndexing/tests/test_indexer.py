"""Unit tests for DataIndexing — no AWS needed.

Run:  python -m pytest Middleware/Workflows/DataIndexing/tests/ -q
  or:  bash Middleware/Workflows/DataIndexing/scripts/run_local.sh
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indexer.chunker import split_text, CHUNK_SIZE_CHARS, CHUNK_OVERLAP_CHARS  # noqa: E402
from indexer.enricher import enrich_chunks, group_latest_flags  # noqa: E402
from indexer.embedding_config import (  # noqa: E402
    resolve_model, dimensions_for, model_slug, load_config)
from indexer.retry_utils import retry_with_backoff  # noqa: E402
from indexer.loader import extract_text  # noqa: E402


def test_chunker_splits_with_overlap():
    text = " ".join(f"word{i}" for i in range(2000))
    chunks = split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= CHUNK_SIZE_CHARS for c in chunks)
    # consecutive chunks overlap: some words appear in both
    assert set(chunks[0].split()) & set(chunks[1].split())
    # no text lost: every word appears in some chunk
    words = set(text.split())
    assert words == set(" ".join(chunks).split())


def test_chunker_short_text_is_one_chunk():
    assert split_text("hello world") == ["hello world"]
    assert split_text("") == []


def test_enricher_deterministic_ids_and_metadata():
    doc = {"doc_id": "pdf_1", "loan_id": "L1", "loan_type": "home",
           "format": "pdf", "year": 2024, "policy_version": "v3",
           "latest": True, "source_s3_key": "raw/pdf/year=2024/x.pdf"}
    first = enrich_chunks(doc, ["aaa", "bbb"], embedding_model="amazon.titan-embed-text-v2:0")
    second = enrich_chunks(doc, ["aaa", "bbb"], embedding_model="amazon.titan-embed-text-v2:0")
    assert first[0]["chunk_id"] == second[0]["chunk_id"]
    assert first[0]["chunk_id"] != first[1]["chunk_id"]
    assert first[0]["loan_type"] == "home"
    assert first[0]["policy_version"] == "v3"
    assert first[0]["latest"] is True
    # a different model -> different chunk ids (separate vector table)
    other = enrich_chunks(doc, ["aaa"], embedding_model="amazon.titan-embed-text-v1")
    assert other[0]["chunk_id"] != first[0]["chunk_id"]


def test_latest_flags_newest_year_per_loan():
    docs = [{"doc_id": "a", "loan_id": "L1", "year": 2023},
            {"doc_id": "b", "loan_id": "L1", "year": 2024},
            {"doc_id": "c", "loan_id": "L2", "year": 2022}]
    flags = group_latest_flags(docs)
    assert flags == {"a": False, "b": True, "c": True}


def test_embedding_config_default_and_override(tmp_path):
    cfg = tmp_path / "embedding_models.yaml"
    cfg.write_text(
        "default_model: amazon.titan-embed-text-v2:0\n"
        "formats:\n  pdf: cohere.embed-english-v3\n  txt: null\n")
    config = load_config(cfg)
    assert resolve_model("pdf", config=config) == ("cohere.embed-english-v3", "format:pdf")
    assert resolve_model("txt", config=config) == ("amazon.titan-embed-text-v2:0", "default")
    assert resolve_model("csv", config=config) == ("amazon.titan-embed-text-v2:0", "default")
    assert resolve_model("pdf", explicit="amazon.titan-embed-text-v1", config=config) == (
        "amazon.titan-embed-text-v1", "explicit")
    assert dimensions_for("amazon.titan-embed-text-v2:0") == 1024
    assert dimensions_for("amazon.titan-embed-text-v1") == 1536
    assert model_slug("amazon.titan-embed-text-v2:0") == "titan_v2"


def test_retry_backoff_retries_then_succeeds():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("throttled")
        return "ok"

    assert retry_with_backoff(flaky, attempts=5,
                              retryable=lambda e: True, sleep=lambda s: None) == "ok"
    assert attempts["n"] == 3


def test_retry_backoff_gives_up():
    def always_fail():
        raise RuntimeError("boom")

    try:
        retry_with_backoff(always_fail, attempts=2,
                           retryable=lambda e: True, sleep=lambda s: None)
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("should have raised")


def test_loader_csv_and_txt():
    assert "hello" in extract_text("txt", b"hello world")
    assert "a | b" in extract_text("csv", b"a,b\n1,2\n")
    assert extract_text("png", b"\x89PNG...") == ""
    try:
        extract_text("exe", b"")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown format should raise")
