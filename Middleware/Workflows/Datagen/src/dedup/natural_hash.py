"""F019 — natural-hash dedup: the business natural key, normalised and hashed.

Decided by the repo owner (Kishore), 2026-11-12: the natural key is the
FULL CONTENT of the loan —

    (customer, loan_type, amount, rate, tenure, start_date)

This answers DESIGN.md §14 open question #1 and S044 #72.

Rules (DESIGN.md §6):
  - Normalise first: lowercase + trim strings (inner whitespace collapsed
    to a single space), amounts rounded to whole rupees, rates rounded to
    2 decimals, tenure as an integer, dates as ISO YYYY-MM-DD.
  - natural_hash = SHA256(normalised fields joined by "|"), lowercase hex.
  - The hash is claimed atomically in the dedup table (claim_natural_hash
    below; the worker calls it before uploading). The first writer wins;
    a later writer gets a conditional-check failure and skips the file.

The business field "customer" is the customer name. Generator records
store it as "name" (see src/generator/generator.py), so normalise_record
accepts either key. No AWS dependency here: claim_natural_hash only calls
put_item on the table object it is given, and recognises a conditional
failure by the error's response code, so tests can pass a fake table.
"""
import hashlib
import re
from datetime import date, datetime

NATURAL_KEY_FIELDS = ("customer", "loan_type", "amount", "rate", "tenure", "start_date")

_WHITESPACE = re.compile(r"\s+")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


def _norm_text(value):
    """Lowercase, trim, collapse inner whitespace to single spaces."""
    return _WHITESPACE.sub(" ", str(value or "").strip().lower())


def _norm_amount(value):
    """Whole rupees: round to the nearest rupee, as a decimal string."""
    return str(int(round(float(value))))


def _norm_rate(value):
    """Percent, rounded to 2 decimals, always written with 2 decimals,
    so 9.5 and 9.50 hash identically."""
    return f"{round(float(value), 2):.2f}"


def _norm_tenure(value):
    """Tenure in months, as an integer string."""
    return str(int(float(value)))


def _norm_date(value):
    """Start date as ISO YYYY-MM-DD. Accepts date/datetime objects and
    the common written forms (2024-03-12, 12/03/2024, 12-03-2024)."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognised start_date: {value!r}")


def normalise_record(rec):
    """The record's natural key, normalised, as a tuple of strings in
    NATURAL_KEY_FIELDS order."""
    return (
        _norm_text(rec.get("customer", rec.get("name", ""))),
        _norm_text(rec.get("loan_type", "")),
        _norm_amount(rec.get("amount", 0)),
        _norm_rate(rec.get("rate", 0)),
        _norm_tenure(rec.get("tenure", 0)),
        _norm_date(rec.get("start_date", "")),
    )


def natural_hash(rec):
    """64-char lowercase SHA256 hex of the normalised key fields joined
    by "|". Two records hash identically iff their business key matches
    after normalisation; loan_id / branch / channel are not key fields."""
    joined = "|".join(normalise_record(rec))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def claim_natural_hash(table, hash_value, doc_id, loan_id):
    """Claim a natural hash in the dedup table (PK is natural_hash).

    Returns True if this writer won the claim, False if another writer
    already claimed the same hash (a duplicate — the caller must skip
    the file: no S3 upload, no manifest row). Any other error raises.

    `table` is a DynamoDB Table object (real or fake); no boto3 import
    is needed here. A conditional failure is recognised by the error's
    response code, which is how botocore reports it.
    """
    try:
        table.put_item(
            Item={"natural_hash": hash_value, "doc_id": doc_id, "loan_id": loan_id},
            ConditionExpression="attribute_not_exists(natural_hash)",
        )
        return True
    except Exception as exc:  # noqa: BLE001 — inspect the AWS error code
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            return False
        raise
