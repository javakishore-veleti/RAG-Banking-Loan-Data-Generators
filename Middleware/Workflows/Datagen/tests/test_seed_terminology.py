"""F016 — real-artifact seeding tests.

Verifies that data/seeds/terminology.yaml loads, that every term traces
to a seed artifact listed in data/seeds/SEEDS.md, that generated
descriptions actually contain seed terminology, and that determinism
and the standalone fallback still hold.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import random

from generator import generator as genmod
from generator.generator import (
    TERMINOLOGY, _load_yaml_subset, _seed_texts, answer_for,
    lines_for, load_terminology, make_record,
)

DATAGEN = Path(__file__).resolve().parents[1]
SEEDS_MD = DATAGEN / "data" / "seeds" / "SEEDS.md"
TERMINOLOGY_YAML = DATAGEN / "data" / "seeds" / "terminology.yaml"
LOAN_TYPES = ["home", "personal", "business", "auto", "education", "gold", "msme"]


def _seed_ids():
    """Seed IDs are the `### <ID> — ...` headings in SEEDS.md."""
    text = SEEDS_MD.read_text(encoding="utf-8")
    return set(re.findall(r"^### ([A-Z][A-Z0-9-]+) —", text, flags=re.M))


def test_terminology_loads_with_all_loan_types():
    assert TERMINOLOGY, "terminology.yaml did not load"
    assert set(TERMINOLOGY["loan_types"]) == set(LOAN_TYPES)
    for key in LOAN_TYPES:
        lt = TERMINOLOGY["loan_types"][key]
        assert lt["label"], key
        assert float(lt["rate_min"]) < float(lt["rate_max"]), key
        assert _seed_texts(lt.get("purposes")), key
        assert _seed_texts(lt.get("documents")), key
        assert _seed_texts(lt.get("terms")), key
        assert lt.get("tenures"), key


def test_every_term_traces_to_a_listed_seed():
    ids = _seed_ids()
    assert len(ids) >= 20, f"only {len(ids)} seeds listed in SEEDS.md"
    for key in LOAN_TYPES:
        lt = TERMINOLOGY["loan_types"][key]
        for section in ("purposes", "documents", "terms", "fees"):
            for entry in lt.get(section) or []:
                assert isinstance(entry, dict), (key, section, entry)
                assert entry.get("text"), (key, section, entry)
                assert entry.get("source") in ids, (key, section, entry)
        for src in lt.get("rate_sources") or []:
            assert src in ids, (key, src)
    for entry in TERMINOLOGY.get("common", {}).get("terms") or []:
        assert entry.get("source") in ids, entry
    for entry in TERMINOLOGY.get("common", {}).get("complaint_products") or []:
        assert entry.get("source") in ids, entry


def test_generated_descriptions_contain_seed_terminology():
    assert TERMINOLOGY, "terminology not loaded"
    seen_types = set()
    for i in range(200):
        rec = make_record(random.Random(1000 + i), i)
        seen_types.add(rec["type_key"])
        text = "\n".join(lines_for(rec)).lower()
        lt = TERMINOLOGY["loan_types"][rec["type_key"]]
        pool = (_seed_texts(lt.get("terms")) + _seed_texts(lt.get("fees"))
                + _seed_texts(lt.get("documents")))
        assert any(t.lower() in text for t in pool), rec["loan_id"]
        assert "key terms:" in text, rec["loan_id"]
    assert seen_types == set(LOAN_TYPES), seen_types


def test_documents_answer_uses_seed_checklist():
    found = 0
    for i in range(300):
        rec = make_record(random.Random(5000 + i), i)
        if rec["topic"] != "documents":
            continue
        lt = TERMINOLOGY["loan_types"][rec["type_key"]]
        docs = [d.lower() for d in _seed_texts(lt.get("documents"))]
        ans = answer_for(rec).lower()
        assert any(d in ans for d in docs), rec
        found += 1
        if found >= 7:
            break
    assert found >= 7, "too few documents-topic records generated"


def test_determinism_still_holds():
    a = make_record(random.Random(7), 0)
    b = make_record(random.Random(7), 0)
    assert a == b
    assert lines_for(a) == lines_for(b)
    # seeded rates stay inside the sourced band for every loan type
    for i in range(100):
        rec = make_record(random.Random(i), i)
        lt = TERMINOLOGY["loan_types"][rec["type_key"]]
        assert float(lt["rate_min"]) <= rec["rate"] <= float(lt["rate_max"])


def test_tenure_answer_matches_seeded_max():
    # A record drawn with a seeded tenure (e.g. gold 36 months) must not
    # be told the product tops out at the old built-in max (24 months).
    checked = 0
    for i in range(300):
        rec = make_record(random.Random(9000 + i), i)
        assert rec["tenure"] <= rec["max_tenure"]
        if rec["topic"] == "tenure":
            ans = answer_for(rec)
            if "up to" in ans:
                assert f"up to {rec['max_tenure']} months" in ans, ans
                checked += 1
    assert checked >= 5, "too few tenure-topic records generated"


def test_generator_works_without_terminology():
    assert load_terminology("/nonexistent/terminology.yaml") == {}
    old = genmod.TERMINOLOGY
    try:
        genmod.TERMINOLOGY = {}
        rec = make_record(random.Random(7), 0)
        assert rec["loan_id"]
        assert rec["seed_terms"] == []
        assert rec["seed_documents"] == []
        assert answer_for(rec)
        assert lines_for(rec)
    finally:
        genmod.TERMINOLOGY = old


def test_yaml_subset_parser_matches_pyyaml():
    # The worker image has no PyYAML, so the built-in subset parser must
    # read the same file the same way. (If PyYAML is absent here, both
    # sides use the subset parser and the comparison is trivially true.)
    text = TERMINOLOGY_YAML.read_text(encoding="utf-8")
    parsed = _load_yaml_subset(text)
    assert set(parsed["loan_types"]) == set(LOAN_TYPES)
    for key in LOAN_TYPES:
        a, b = parsed["loan_types"][key], TERMINOLOGY["loan_types"][key]
        assert a["rate_min"] == b["rate_min"] and a["rate_max"] == b["rate_max"]
        assert _seed_texts(a.get("purposes")) == _seed_texts(b.get("purposes"))
        assert _seed_texts(a.get("terms")) == _seed_texts(b.get("terms"))
        assert _seed_texts(a.get("documents")) == _seed_texts(b.get("documents"))
        assert _seed_texts(a.get("fees")) == _seed_texts(b.get("fees"))
    assert parsed["common"]["terms"] == TERMINOLOGY["common"]["terms"]
    assert parsed["common"]["complaint_products"] == TERMINOLOGY["common"]["complaint_products"]
