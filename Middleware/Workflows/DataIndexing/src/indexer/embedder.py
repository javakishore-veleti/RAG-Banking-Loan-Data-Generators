"""L3 — embed chunk texts with Amazon Bedrock.

Retry + failover mechanics (the part the video does not show, and the
part that matters in production):
  - Throttling / transient Bedrock errors: exponential backoff with
    jitter, 5 attempts (see retry_utils).
  - Model failover: if the configured model is rejected (not enabled in
    Bedrock, access denied, unknown id), fall back to the default model
    ONCE for this batch and return the model actually used, so the
    chunk metadata records the truth. A failed default raises.
  - Unknown model dimensions: probe with one embedding and measure the
    returned vector length; the stores use that to size the table.

One Bedrock call embeds a batch of texts in a single InvokeModel call
per text (Bedrock embedding models take one inputText per call); calls
are sequential in this worker — Batch scales by running many workers,
not by threading inside one shard.
"""

import json
import os

import boto3
from botocore.config import Config

from indexer.embedding_config import DEFAULT_MODEL, dimensions_for
from indexer.retry_utils import retry_with_backoff

REGION = os.environ.get("AWS_REGION", "ap-south-1")
_RETRY = Config(retries={"max_attempts": 5, "mode": "adaptive"})

# Bedrock errors worth retrying with backoff.
_RETRYABLE = ("ThrottlingException", "Throttling", "ServiceUnavailableException",
              "InternalServerException", "ModelTimeoutException")
# Bedrock errors that mean "this model cannot be used" -> fail over.
_FAILOVER = ("AccessDeniedException", "ValidationException", "ResourceNotFoundException")


def _is_retryable(exc):
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    return code in _RETRYABLE or type(exc).__name__ == "EndpointConnectionError"


def _is_failover(exc):
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    return code in _FAILOVER


class BedrockEmbedder:
    def __init__(self, client=None, region=REGION):
        self.client = client or boto3.client("bedrock-runtime", region_name=region,
                                             config=_RETRY)

    def embed_one(self, model_id, text):
        """One embedding vector (list of floats) for one text."""
        body = json.dumps({"inputText": text})
        resp = retry_with_backoff(
            lambda: self.client.invoke_model(modelId=model_id, body=body),
            attempts=5, retryable=_is_retryable)
        return json.loads(resp["body"].read())["embedding"]

    def embed_batch(self, model_id, texts, *, default_model=DEFAULT_MODEL):
        """Embed `texts` with `model_id`. Returns (vectors, model_used).
        On a model-level failure, fails over to `default_model` once;
        if the default also fails, the exception propagates (the shard
        is redriven by SQS, then lands in the DLQ — never silently lost)."""
        try:
            vectors = [self.embed_one(model_id, t) for t in texts]
            return vectors, model_id
        except Exception as exc:  # noqa: BLE001 — failover decision below
            if _is_failover(exc) and model_id != default_model:
                vectors = [self.embed_one(default_model, t) for t in texts]
                return vectors, default_model
            raise

    def probe_dimensions(self, model_id):
        """Vector length for `model_id`; falls back to the config table."""
        dims = dimensions_for(model_id)
        if dims:
            return dims
        return len(self.embed_one(model_id, "dimension probe"))
