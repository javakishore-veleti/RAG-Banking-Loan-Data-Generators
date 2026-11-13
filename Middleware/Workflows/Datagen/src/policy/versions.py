"""F018 — Policy corpus version table (single source of truth).

One policy version per loan type per year. A customer record references
the version in force for its loan type in its start year
(`policy_version`, e.g. ``home-v2024-01``).

Versions are deliberately few: policy documents are versioned rules,
not per-loan records — see DESIGN.md §3.2. Only two versions exist
because only one fetch snapshot of the source material exists
(terminology.yaml, fetched 2026-11-12); no historical figures were
invented. When a refresh fetches new figures, add a new version here
(e.g. ``v2025-01``) and record what changed in data/policies/POLICIES.md.
"""
# loan_type -> [(version, effective_date)] oldest first.
POLICY_VERSIONS = {
    "home": [("v2023-01", "2023-01-01"), ("v2024-01", "2024-01-01")],
    "personal": [("v2023-01", "2023-01-01"), ("v2024-01", "2024-01-01")],
    "business": [("v2023-01", "2023-01-01"), ("v2024-01", "2024-01-01")],
    "auto": [("v2023-01", "2023-01-01"), ("v2024-01", "2024-01-01")],
    "education": [("v2023-01", "2023-01-01"), ("v2024-01", "2024-01-01")],
    "gold": [("v2023-01", "2023-01-01"), ("v2024-01", "2024-01-01")],
    "msme": [("v2023-01", "2023-01-01"), ("v2024-01", "2024-01-01")],
}


def version_id(loan_type, version):
    """Full version id, e.g. ``home-v2024-01``."""
    return f"{loan_type}-{version}"


def versions_for(loan_type):
    """[(version, effective_date)] oldest first for this loan type."""
    return list(POLICY_VERSIONS[loan_type])


def version_ids_for(loan_type):
    """Full version ids for this loan type, oldest first."""
    return [version_id(loan_type, v) for v, _ in POLICY_VERSIONS[loan_type]]


def latest_version(loan_type):
    """Full version id of the latest version for this loan type."""
    return version_id(loan_type, POLICY_VERSIONS[loan_type][-1][0])


def effective_date(loan_type, version):
    """Effective date (YYYY-MM-DD) of a version, e.g. ``2024-01-01``."""
    for v, eff in POLICY_VERSIONS[loan_type]:
        if v == version:
            return eff
    raise KeyError(f"unknown policy version {loan_type}-{version}")


def supersedes(loan_type, version):
    """Full version id this version replaces, or None for the first."""
    versions = POLICY_VERSIONS[loan_type]
    for i, (v, _eff) in enumerate(versions):
        if v == version:
            return version_id(loan_type, versions[i - 1][0]) if i > 0 else None
    raise KeyError(f"unknown policy version {loan_type}-{version}")


def is_latest(loan_type, version):
    """True if this is the newest version for the loan type."""
    return version == POLICY_VERSIONS[loan_type][-1][0]


def policy_version_for(loan_type, year):
    """Policy version in force for a loan of this type in this year.

    The greatest version whose year is <= the loan's start year; a
    loan starting before the first version uses the first version, and
    a loan starting after the latest version uses the latest version
    (it stays in force until superseded). Deterministic.
    """
    year = int(year)
    chosen = None
    for version, _eff in POLICY_VERSIONS[loan_type]:
        version_year = int(version[1:5])
        if version_year <= year:
            chosen = version
        else:
            break
    if chosen is None:
        chosen = POLICY_VERSIONS[loan_type][0][0]
    return version_id(loan_type, chosen)


def all_version_ids():
    """Every full version id, e.g. ``home-v2024-01``."""
    return [version_id(lt, v) for lt, vs in POLICY_VERSIONS.items()
            for v, _ in vs]
