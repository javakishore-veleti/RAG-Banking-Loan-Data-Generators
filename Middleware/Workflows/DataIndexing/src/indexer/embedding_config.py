"""Embedding-model resolution — one model per document type, default fallback.

Resolution order (highest wins):
  1. explicit model passed by the caller (workflow_dispatch input
     `embedding_model`, or `EMBEDDING_MODEL` env) — if non-empty.
  2. the per-format override in config/embedding_models.yaml.
  3. `default_model` from the same config file.

`formats.<fmt>: null` means "no override — use the default". A model id
that is not in the config's `dimensions` table is still usable: the
embedder measures the vector length from a probe embedding instead.
"""

import os
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "embedding_models.yaml"

# Dimensions for Bedrock embedding models we know about. Kept here (not
# only in the YAML) so tests and the stores can resolve dims without a file.
KNOWN_DIMENSIONS = {
    "amazon.titan-embed-text-v2:0": 1024,
    "amazon.titan-embed-text-v1": 1536,
    "cohere.embed-english-v3": 1024,
    "cohere.embed-multilingual-v3": 1024,
}

DEFAULT_MODEL = "amazon.titan-embed-text-v2:0"


def load_config(path=None):
    """Load embedding_models.yaml.
    Returns (default_model, {format: model|None}, {model: dims}).
    Missing/unreadable file -> the built-in default, no overrides."""
    path = Path(path or os.environ.get("EMBEDDING_CONFIG", DEFAULT_CONFIG))
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return DEFAULT_MODEL, {}, dict(KNOWN_DIMENSIONS)
    default = data.get("default_model") or DEFAULT_MODEL
    formats = data.get("formats") or {}
    dims = dict(KNOWN_DIMENSIONS)
    dims.update(data.get("dimensions") or {})
    return default, {k: v for k, v in formats.items()}, dims


def resolve_model(fmt, *, explicit=None, config=None):
    """Model id to embed `fmt` (e.g. 'pdf') with, plus where it came from."""
    explicit = explicit or os.environ.get("EMBEDDING_MODEL") or None
    if explicit:
        return explicit, "explicit"
    default, overrides, _dims = config or load_config()
    override = overrides.get(fmt)
    if override:
        return override, f"format:{fmt}"
    return default, "default"


def dimensions_for(model_id, *, config=None):
    """Vector dimensions for a model id, or None if unknown here."""
    if config:
        _default, _overrides, dims = config
        if model_id in dims:
            return dims[model_id]
    return KNOWN_DIMENSIONS.get(model_id)


def model_slug(model_id):
    """Filesystem/table-safe slug: 'amazon.titan-embed-text-v2:0' -> 'titan_v2'."""
    import re
    slug = model_id.split("/")[-1]
    slug = re.sub(r":\d+$", "", slug)  # drop the Bedrock version suffix (:0)
    slug = slug.replace("amazon.", "").replace("cohere.", "")
    slug = slug.replace("-embed-text-", "_").replace("-embed-", "_")
    slug = slug.replace(".", "_").replace(":", "_").replace("-", "_")
    return slug or "unknown"
