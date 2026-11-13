"""F018 — policy corpus tests.

Verifies the versioned policy corpus (src/policy/): version ids are
unique with exactly one latest per loan type, the corpus stays small
(tens of documents, not thousands), every rule traces to a seed
artifact listed in data/seeds/SEEDS.md, and every customer record's
policy_version references a policy version that actually exists.
"""
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import generator.generator as genmod
from generator.generator import lines_for, make_record, policy_version_for_record
from policy.policy_generator import TOPIC_LABELS, build_policies, lines_for_policy
from policy.versions import (
    POLICY_VERSIONS, all_version_ids, is_latest, latest_version,
    policy_version_for, supersedes, version_ids_for,
)

DATAGEN = Path(__file__).resolve().parents[1]
SEEDS_MD = DATAGEN / "data" / "seeds" / "SEEDS.md"
LOAN_TYPES = ["home", "personal", "business", "auto", "education", "gold", "msme"]

# Topics each loan type is expected to have, from the sourced material
# in terminology.yaml. Business/MSME have no sourced prepayment rule,
# auto has no sourced fees list, gold alone has the LTV rule — those
# topics are omitted, not invented.
EXPECTED_TOPICS = {
    "home": {"interest-rate", "prepayment", "documents", "fees", "tenure"},
    "personal": {"interest-rate", "prepayment", "documents", "fees", "tenure"},
    "business": {"interest-rate", "documents", "fees", "tenure"},
    "auto": {"interest-rate", "prepayment", "documents", "tenure"},
    "education": {"interest-rate", "prepayment", "documents", "fees", "tenure"},
    "gold": {"interest-rate", "prepayment", "documents", "fees", "tenure", "ltv"},
    "msme": {"interest-rate", "documents", "fees", "tenure"},
}


def _seed_ids():
    """Seed IDs are the `### <ID> — ...` headings in SEEDS.md."""
    text = SEEDS_MD.read_text(encoding="utf-8")
    return set(re.findall(r"^### ([A-Z][A-Z0-9-]+) —", text, flags=re.M))


def test_policy_versions_unique_and_latest():
    for key in LOAN_TYPES:
        ids = version_ids_for(key)
        assert len(ids) == len(set(ids)), key
        assert len(ids) == 2, key  # v2023-01 and v2024-01
        latest = [v for v in ("v2023-01", "v2024-01") if is_latest(key, v)]
        assert latest == ["v2024-01"], key
        assert latest_version(key) == f"{key}-v2024-01", key
        assert supersedes(key, "v2023-01") is None, key
        assert supersedes(key, "v2024-01") == f"{key}-v2023-01", key
    assert len(all_version_ids()) == 14
    assert len(set(all_version_ids())) == 14


def test_policy_version_for_year_edges():
    for key in LOAN_TYPES:
        assert policy_version_for(key, 2022) == f"{key}-v2023-01", key
        assert policy_version_for(key, 2023) == f"{key}-v2023-01", key
        assert policy_version_for(key, 2024) == f"{key}-v2024-01", key
        assert policy_version_for(key, 2025) == f"{key}-v2024-01", key
        assert policy_version_for(key, 2030) == f"{key}-v2024-01", key


def test_policy_count_is_small():
    policies = build_policies()
    # 33 rules per version x 2 versions = 66 documents. Tens, not
    # thousands — the whole point of a separate policy corpus.
    assert len(policies) == 66, len(policies)
    assert 20 <= len(policies) <= 100
    by_type_version = {}
    for pol in policies:
        by_type_version.setdefault((pol["loan_type"], pol["version"]), set()).add(pol["topic"])
    for key in LOAN_TYPES:
        for version in ("v2023-01", "v2024-01"):
            topics = by_type_version[(key, f"{key}-{version}")]
            assert topics == EXPECTED_TOPICS[key], (key, version, topics)


def test_policy_ids_unique_and_latest_flag():
    policies = build_policies()
    ids = [p["policy_id"] for p in policies]
    assert len(ids) == len(set(ids))
    for key in LOAN_TYPES:
        latest = [p for p in policies
                  if p["loan_type"] == key and p["latest"]]
        assert len(latest) == len(EXPECTED_TOPICS[key]), key
        assert all(p["version"] == f"{key}-v2024-01" for p in latest), key
        old = [p for p in policies
               if p["loan_type"] == key and not p["latest"]]
        assert all(p["supersedes"] is None for p in old), key
        assert all(p["supersedes"] == f"{key}-v2023-01" for p in latest), key


def test_policy_rules_trace_to_seeds():
    ids = _seed_ids()
    assert len(ids) >= 20, f"only {len(ids)} seeds listed in SEEDS.md"
    for pol in build_policies():
        assert pol["rule"].strip(), pol["policy_id"]
        assert pol["sources"], pol["policy_id"]
        for src in pol["sources"]:
            assert src in ids, (pol["policy_id"], src)
        assert pol["topic"] in TOPIC_LABELS, pol["policy_id"]
        text = "\n".join(lines_for_policy(pol))
        assert pol["policy_id"] in text
        assert pol["version"] in text
        assert pol["rule"] in text


def test_policy_build_is_deterministic():
    assert build_policies() == build_policies()
    a = lines_for_policy(build_policies()[0])
    b = lines_for_policy(build_policies()[0])
    assert a == b


def test_every_customer_policy_version_exists():
    existing = {key: set(version_ids_for(key)) for key in LOAN_TYPES}
    seen_types = set()
    for i in range(500):
        year = [2022, 2023, 2024, 2025, None][i % 5]
        rec = make_record(random.Random(7000 + i), i, year=year)
        seen_types.add(rec["type_key"])
        assert rec["policy_version"] in existing[rec["type_key"]], rec
        assert rec["policy_version"].startswith(rec["type_key"] + "-v"), rec
    assert seen_types == set(LOAN_TYPES), seen_types


def test_customer_generator_shows_policy_version():
    rec = make_record(random.Random(7), 0, year=2024)
    assert rec["policy_version"]
    assert rec["policy_version"].startswith(rec["type_key"] + "-v2024-01")
    rec2023 = make_record(random.Random(7), 0, year=2023)
    assert rec2023["policy_version"].endswith("-v2023-01")
    # The policy version line appears in all three layouts.
    for layout in (0, 1, 2):
        rec["layout"] = layout
        text = "\n".join(lines_for(rec))
        assert f"Policy Version: {rec['policy_version']}" in text, layout


def test_policy_version_fallback_agrees_with_module():
    # generator.py falls back to a year-clamp rule when src/policy/ is
    # not importable (standalone copy). It must give the same answers
    # as the version table.
    old = genmod._policy_version_for
    try:
        genmod._policy_version_for = None
        for key in LOAN_TYPES:
            for year in (2022, 2023, 2024, 2025, 2030):
                assert policy_version_for_record(key, year) == policy_version_for(key, year), (key, year)
    finally:
        genmod._policy_version_for = old
