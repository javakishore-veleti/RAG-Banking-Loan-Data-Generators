"""Natural-hash dedup (F019): normalise the business key, hash it, claim it."""
from dedup.natural_hash import NATURAL_KEY_FIELDS, claim_natural_hash, natural_hash, normalise_record

__all__ = ["NATURAL_KEY_FIELDS", "claim_natural_hash", "natural_hash", "normalise_record"]
