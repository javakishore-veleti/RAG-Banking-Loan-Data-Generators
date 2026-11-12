"""Small retry helper — exponential backoff with jitter.

Used by the Bedrock embedder (throttling) and the stores (transient DB
errors). Retries are bounded and logged; when they run out, the caller
lets the failure surface so SQS / Step Functions redrive the shard
instead of silently dropping a document.
"""

import random
import time


def retry_with_backoff(fn, *, attempts=5, base_seconds=1.0, max_seconds=30.0,
                       retryable, sleep=time.sleep):
    """Call fn(); on an exception for which retryable(exc) is true, retry
    with exponential backoff + jitter. Returns fn()'s value, or re-raises
    the last exception after `attempts` tries."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — re-raised below if fatal
            last = exc
            if not retryable(exc) or attempt == attempts:
                raise
            delay = min(max_seconds, base_seconds * (2 ** (attempt - 1)))
            delay = delay * (0.5 + random.random())  # jitter: 0.5x–1.5x
            sleep(delay)
    raise last  # pragma: no cover — loop always returns or raises
