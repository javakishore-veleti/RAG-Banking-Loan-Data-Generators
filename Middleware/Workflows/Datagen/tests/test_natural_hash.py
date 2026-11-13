"""F019 — natural-hash dedup tests.

Verifies the business natural key (full content, decided by the repo
owner 2026-11-12): normalisation makes spelling/case/rounding/date
variants hash identically, different key fields hash differently,
the atomic claim lets the first writer win, and generator records
carry a deterministic natural_hash.

The worker module itself (batch_worker.py) imports boto3, which is not
installed locally, so the claim logic is tested here through
dedup.natural_hash.claim_natural_hash with a fake table — the worker
calls that same function.
"""
import random
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import generator.generator as genmod
from dedup.natural_hash import (
    NATURAL_KEY_FIELDS,
    claim_natural_hash,
    natural_hash,
    normalise_record,
)
from generator.generator import make_record, natural_hash_for_record

BASE = {
    "customer": "Arjun Kulkarni", "loan_type": "Business Loan",
    "amount": 1500000, "rate": 9.5, "tenure": 60,
    "start_date": "2024-03-12",
    "loan_id": "LN123456000001", "branch": "Mumbai Main",
}

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class _ConditionalCheckFailed(Exception):
    """Stands in for botocore's ClientError with a conditional-check code."""

    def __init__(self):
        super().__init__("The conditional request failed")
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class _OtherError(Exception):
    def __init__(self):
        super().__init__("Something else failed")
        self.response = {"Error": {"Code": "ValidationException"}}


class FakeTable:
    """Minimal stand-in for a DynamoDB Table with a natural_hash PK."""

    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        key = Item["natural_hash"]
        if (ConditionExpression == "attribute_not_exists(natural_hash)"
                and key in self.items):
            raise _ConditionalCheckFailed()
        self.items[key] = Item
        return {}


def test_key_fields_are_the_decided_full_content():
    assert NATURAL_KEY_FIELDS == (
        "customer", "loan_type", "amount", "rate", "tenure", "start_date")


def test_hash_is_64_char_lowercase_hex():
    h = natural_hash(BASE)
    assert _HEX64.match(h), h


def test_normalisation_variants_hash_identically():
    base = natural_hash(BASE)
    variants = [
        {**BASE, "customer": "  arjun   kulkarni "},       # case + spaces
        {**BASE, "loan_type": "business loan"},             # case
        {**BASE, "amount": 1500000.0},                      # float amount
        {**BASE, "amount": 1500000.4},                      # rounds to whole
        {**BASE, "rate": 9.50},                             # 9.5 == 9.50
        {**BASE, "rate": 9.500},                            # same again
        {**BASE, "tenure": "60"},                           # string tenure
        {**BASE, "start_date": "12/03/2024"},               # DD/MM/YYYY
        {**BASE, "start_date": "12-03-2024"},               # DD-MM-YYYY
        {**BASE, "start_date": date(2024, 3, 12)},          # date object
    ]
    for v in variants:
        assert natural_hash(v) == base, v


def test_generator_name_field_is_the_customer():
    # Generator records store the customer name as "name", not
    # "customer" — both spellings must hash identically.
    rec = {**BASE}
    rec["name"] = rec.pop("customer")
    assert natural_hash(rec) == natural_hash(BASE)


def test_same_key_different_ids_same_hash():
    other = {**BASE, "loan_id": "LN999999000002", "branch": "Delhi South"}
    assert natural_hash(other) == natural_hash(BASE)


def test_different_key_fields_hash_differently():
    base = natural_hash(BASE)
    for change in (
        {"customer": "Meera Nair"},
        {"loan_type": "Home Loan"},
        {"amount": 1500001},
        {"amount": 2000000},
        {"rate": 9.51},
        {"tenure": 61},
        {"start_date": "2024-03-13"},
    ):
        assert natural_hash({**BASE, **change}) != base, change


def test_claim_first_wins_second_returns_false():
    table = FakeTable()
    h = natural_hash(BASE)
    assert claim_natural_hash(table, h, "pdf_0000000", "LN123456000001") is True
    assert table.items[h]["doc_id"] == "pdf_0000000"
    assert table.items[h]["loan_id"] == "LN123456000001"
    # Same hash, different doc — the second writer loses.
    assert claim_natural_hash(table, h, "pdf_0000001", "LN999999000002") is False
    assert table.items[h]["doc_id"] == "pdf_0000000"  # first claim stands
    # A different hash still claims fine.
    assert claim_natural_hash(
        table, natural_hash({**BASE, "amount": 2000000}),
        "pdf_0000002", "LN123456000003") is True


def test_claim_other_errors_raise():
    class FailingTable(FakeTable):
        def put_item(self, Item, ConditionExpression=None):
            raise _OtherError()

    try:
        claim_natural_hash(FailingTable(), natural_hash(BASE), "pdf_1", "LN1")
    except _OtherError:
        pass  # expected: only conditional failures become False
    else:
        raise AssertionError("non-conditional errors must raise")


def test_generator_records_carry_deterministic_hash():
    # One shared RNG per run: a fresh Random(7) per record would replay
    # the same first draw twenty times (only loan_id differs).
    rng = random.Random(7)
    recs = [make_record(rng, i, year=2024) for i in range(20)]
    a = [r["natural_hash"] for r in recs]
    rng2 = random.Random(7)
    b = [make_record(rng2, i, year=2024)["natural_hash"] for i in range(20)]
    assert a == b
    assert all(_HEX64.match(h) for h in a)
    # Hashes track the key exactly: same hash iff same normalised key.
    assert len(set(a)) == len({normalise_record(r) for r in recs})
    assert len(set(a)) > 1


def test_natural_hash_fallback_agrees_with_module():
    # generator.py falls back to its own copy of the rules when
    # src/dedup/ is not importable (standalone copy). It must give the
    # same answers as the module.
    from dedup.natural_hash import natural_hash as module_hash

    samples = [BASE, {**BASE, "customer": "  MEERA  NAIR "},
               {**BASE, "amount": 1500000.0, "rate": 9.50,
                "start_date": date(2024, 3, 12)},
               {**BASE, "name": "Arjun Kulkarni"}]
    # The last sample has both keys; "customer" wins in both paths.
    samples[-1].pop("customer")
    old = genmod._natural_hash
    try:
        genmod._natural_hash = None
        for rec in samples:
            assert natural_hash_for_record(rec) == module_hash(rec), rec
    finally:
        genmod._natural_hash = old


def test_normalise_record_output_shape():
    assert normalise_record(BASE) == (
        "arjun kulkarni", "business loan", "1500000", "9.50", "60",
        "2024-03-12")
