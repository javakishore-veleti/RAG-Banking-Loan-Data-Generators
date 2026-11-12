import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import random

from generator.generator import answer_for, emi, make_record


def test_emi_is_positive_and_reasonable():
    assert 0 < emi(1_000_000, 10.0, 12) < 100_000


def test_records_are_deterministic_per_seed():
    a = make_record(random.Random(7), 0)
    b = make_record(random.Random(7), 0)
    assert a == b


def test_record_has_all_fields_and_answer_mentions_loan():
    rec = make_record(random.Random(7), 0)
    for field in ("loan_id", "loan_type", "amount", "rate", "tenure", "emi", "question"):
        assert rec[field]
    assert rec["loan_id"] in answer_for(rec)
    assert rec["amount"] > 0 and rec["emi"] > 0
