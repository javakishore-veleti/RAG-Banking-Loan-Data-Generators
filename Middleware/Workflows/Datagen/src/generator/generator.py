#!/usr/bin/env python3
"""
RAG Corpus Generator — Banking Loans
=====================================
Generate 1 million (or any N) documents of EACH type, from the same
underlying loan records, so a RAG system can be tested across formats:

    pdf, docx, xlsx, csv, txt, png

    python3 rag_corpus_generator.py --count 10 --out ./corpus
    python3 rag_corpus_generator.py --count 1000000 --out ./corpus --formats pdf,csv,txt
    python3 rag_corpus_generator.py --count 1000 --out ./corpus --seed 42 --workers 4

What it generates per record (one loan, one question/answer):
  - PDF  : loan product / sanction summary sheet
  - DOCX : loan application summary document
  - XLSX : EMI schedule workbook
  - CSV  : loan record table (one file per record)
  - TXT  : FAQ / support answer text
  - PNG  : loan summary card rendered as an image (needs OCR in RAG)

Also writes:
  - manifest.jsonl : ground truth — doc_id, format, loan_id, question, answer, file
  - README.txt     : counts, sizes, how to scale

Design notes (realism):
  - Same loan record rendered in all 6 formats, so retrieval can be
    compared across parsers with known ground truth.
  - Amounts / rates / tenures use realistic clustered ranges per loan
    type, not uniform random numbers.
  - Names, loan IDs, branches, dates are fictional.
  - No external dependencies required for pdf/docx/xlsx/csv/txt.
    PNG uses Pillow if available, otherwise a plain PNG fallback.
  - 1M per format = 6M files. That is tens of GB and will take hours
    on a normal machine. Start with 1,000 per format, test ingestion,
    then scale up. Use --formats to generate one format at a time.

Usage: python3 rag_corpus_generator.py --count N --out DIR [--seed S]
"""
import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import struct
import sys
import zipfile
import zlib
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------- seeds (F016)
# Real-artifact terminology lives in data/seeds/terminology.yaml and is
# loaded at runtime when present. The generator keeps working standalone
# without it: load_terminology() returns {} and make_record() falls back
# to the built-in LOAN_TYPES ranges, purposes and tenures.
# The worker image has no PyYAML, so a minimal built-in parser for this
# file's shape is used when `import yaml` fails.
SEED_TERMINOLOGY_ENV = "SEED_TERMINOLOGY_PATH"


def _seed_terminology_candidates():
    here = Path(__file__).resolve()
    cands = []
    env = os.environ.get(SEED_TERMINOLOGY_ENV)
    if env:
        cands.append(Path(env))
    # Datagen layout: src/generator/generator.py -> data/seeds/terminology.yaml
    cands.append(here.parents[2] / "data" / "seeds" / "terminology.yaml")
    # Worker image layout: /app/src/generator/generator.py -> /app/data/seeds/...
    cands.append(Path("/app/data/seeds/terminology.yaml"))
    return cands


def _yaml_scalar(value):
    """One plain YAML scalar: quoted string, int, float, bool, or string."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    if v in ("true", "True"):
        return True
    if v in ("false", "False"):
        return False
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _load_yaml_subset(text):
    """Minimal YAML-subset parser, just for terminology.yaml's shape.

    Supports nested mappings by 2-space indent, scalar values, lists of
    scalars, and lists of mappings written as '- key: value' with the
    remaining keys at the same indent. Anything else raises ValueError.
    """
    root = {}
    stack = [(-1, root)]  # (indent, container)
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValueError("bad indentation in terminology.yaml")
        parent = stack[-1][1]
        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError("list item without a list in terminology.yaml")
            item_text = content[2:].strip()
            if ":" in item_text:
                key, _, val = item_text.partition(":")
                item = {key.strip(): _yaml_scalar(val.strip())}
                parent.append(item)
                # continuation keys sit at indent + 2; keep the item open
                # for any line indented deeper than the dash itself.
                stack.append((indent, item))
            else:
                parent.append(_yaml_scalar(item_text))
            continue
        if not isinstance(parent, dict):
            raise ValueError("mapping entry inside a list in terminology.yaml")
        key, _, val = content.partition(":")
        key, val = key.strip(), val.strip()
        if not key:
            raise ValueError("empty key in terminology.yaml")
        if val == "":
            # peek at the next real line to decide list vs mapping
            j = i
            while j < len(lines) and (not lines[j].strip()
                                      or lines[j].lstrip().startswith("#")):
                j += 1
            if j < len(lines) and lines[j].strip().startswith("- "):
                child = []
            else:
                child = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _yaml_scalar(val)
    return root


def load_terminology(path=None):
    """Load data/seeds/terminology.yaml; {} if missing or unreadable."""
    paths = [Path(path)] if path else _seed_terminology_candidates()
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            import yaml
            data = yaml.safe_load(text)
        except ImportError:
            try:
                data = _load_yaml_subset(text)
            except ValueError:
                return {}
        except Exception:
            return {}
        if not isinstance(data, dict) or not isinstance(data.get("loan_types"), dict):
            return {}
        return data
    return {}


TERMINOLOGY = load_terminology()


# ---------------------------------------------------------------- policy versions (F018)
# The policy corpus (src/policy/) owns the version table; the customer
# generator only needs the mapping (loan_type, year) -> policy version
# so each record references the policy in force for its start year.
# Import it when the policy module is on the path (Batch worker, tests);
# fall back to the same year-clamp rule when generator.py runs
# standalone without src/policy/ alongside it.
try:
    from policy.versions import policy_version_for as _policy_version_for
except ImportError:  # standalone copy of generator.py
    _policy_version_for = None


def policy_version_for_record(loan_type, year):
    """Policy version in force for a loan of this type in this year."""
    if _policy_version_for is not None:
        return _policy_version_for(loan_type, year)
    y = min(max(int(year), 2023), 2024)
    return f"{loan_type}-v{y}-01"


# ---------------------------------------------------------------- natural hash (F019)
# The dedup module (src/dedup/) owns the natural-key normalisation and
# hashing; the generator only stamps each record. Import it when it is
# on the path (Batch worker, tests); fall back to the same rules when
# generator.py runs standalone without src/dedup/ alongside it.
try:
    from dedup.natural_hash import natural_hash as _natural_hash
except ImportError:  # standalone copy of generator.py
    _natural_hash = None


def _fallback_natural_hash(rec):
    """Same rules as dedup.natural_hash, for standalone runs (see the
    agreement test in tests/test_natural_hash.py). Kept in step with the
    module by that test; change both together."""
    import hashlib as _hashlib
    import re as _re
    from datetime import date as _date, datetime as _datetime

    def _text(v):
        return _re.sub(r"\s+", " ", str(v or "").strip().lower())

    customer = _text(rec.get("customer", rec.get("name", "")))
    loan_type = _text(rec.get("loan_type", ""))
    amount = str(int(round(float(rec.get("amount", 0)))))
    rate = f"{round(float(rec.get('rate', 0)), 2):.2f}"
    tenure = str(int(float(rec.get("tenure", 0))))
    start = rec.get("start_date", "")
    if isinstance(start, _datetime):
        start = start.date()
    if isinstance(start, _date):
        start = start.isoformat()
    else:
        text = str(start or "").strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                start = _datetime.strptime(text, fmt).date().isoformat()
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"unrecognised start_date: {start!r}")
    joined = "|".join((customer, loan_type, amount, rate, tenure, start))
    return _hashlib.sha256(joined.encode("utf-8")).hexdigest()


def natural_hash_for_record(rec):
    """SHA256 of the record's normalised natural key (F019)."""
    if _natural_hash is not None:
        return _natural_hash(rec)
    return _fallback_natural_hash(rec)


def _seed_texts(entries):
    """Pull the plain `text` out of a terminology list (dicts or strings)."""
    out = []
    for e in entries or []:
        if isinstance(e, dict):
            out.append(str(e.get("text", "")))
        else:
            out.append(str(e))
    return [t for t in out if t]


# ---------------------------------------------------------------- content

FIRST_NAMES = [
    "Aarav", "Priya", "Rahul", "Ananya", "Vikram", "Sneha", "Arjun", "Meera",
    "Kiran", "Divya", "Rohan", "Nisha", "Aditya", "Kavya", "Sanjay", "Pooja",
    "James", "Maria", "David", "Sarah", "Michael", "Emma", "Daniel", "Sophia",
    "Ahmed", "Fatima", "Chen", "Li", "Yuki", "Carlos", "Elena", "Omar",
]
LAST_NAMES = [
    "Sharma", "Patel", "Iyer", "Reddy", "Khan", "Das", "Nair", "Gupta",
    "Mehta", "Singh", "Joshi", "Kulkarni", "Smith", "Johnson", "Brown",
    "Garcia", "Kim", "Tanaka", "Ali", "Hassan", "Fernandez", "Costa",
]
BRANCHES = [
    "Mumbai-Andheri", "Delhi-Connaught Place", "Bengaluru-Koramangala",
    "Chennai-T Nagar", "Hyderabad-Hitech City", "Pune-Hinjawadi",
    "Kolkata-Salt Lake", "Ahmedabad-CG Road", "New York-Manhattan",
    "London-Canary Wharf", "Singapore-Raffles Place",
]
# loan_type: (label, amount_min, amount_max, rate_min, rate_max, tenures, purposes)
LOAN_TYPES = {
    "home": ("Home Loan", 500_000, 15_000_000, 8.5, 11.5, [120, 180, 240, 300],
             ["buying a flat", "buying a house", "home construction", "home renovation"]),
    "personal": ("Personal Loan", 50_000, 1_500_000, 10.5, 16.0, [12, 24, 36, 48, 60],
                 ["medical expenses", "wedding expenses", "education", "debt consolidation", "travel"]),
    "business": ("Business Loan", 500_000, 50_000_000, 9.0, 15.0, [12, 24, 36, 60, 84],
                 ["working capital", "equipment purchase", "business expansion", "inventory"]),
    "auto": ("Auto Loan", 200_000, 3_000_000, 8.0, 12.0, [12, 24, 36, 48, 60],
            ["buying a car", "buying a two-wheeler", "buying a commercial vehicle"]),
    "education": ("Education Loan", 100_000, 5_000_000, 9.5, 13.5, [60, 84, 120, 180],
                  ["higher studies in India", "studies abroad", "professional course"]),
    "gold": ("Gold Loan", 25_000, 2_000_000, 9.0, 14.0, [6, 12, 18, 24],
            ["short-term cash need", "agricultural expenses", "business need"]),
    "msme": ("MSME Loan", 100_000, 10_000_000, 8.75, 14.5, [12, 24, 36, 60],
            ["working capital for MSME", "machinery purchase", "shop expansion"]),
}
CHANNELS = ["loan customers", "customer support", "partners"]

QUESTIONS = {
    "home": [
        ("What is the interest rate for a home loan?", "interest rate"),
        ("What documents are needed for a home loan?", "documents"),
        ("How is home loan EMI calculated?", "emi"),
        ("What is the maximum tenure for a home loan?", "tenure"),
    ],
    "personal": [
        ("What is the interest rate for a personal loan?", "interest rate"),
        ("What is the eligibility for a personal loan?", "eligibility"),
        ("What documents are needed for a personal loan?", "documents"),
        ("Can I prepay my personal loan?", "prepayment"),
    ],
    "business": [
        ("What is the interest rate for a business loan?", "interest rate"),
        ("What documents are needed for a business loan?", "documents"),
        ("What is the maximum amount for a business loan?", "amount"),
    ],
    "auto": [
        ("What is the interest rate for an auto loan?", "interest rate"),
        ("What is the tenure for an auto loan?", "tenure"),
        ("What documents are needed for an auto loan?", "documents"),
    ],
    "education": [
        ("What is the interest rate for an education loan?", "interest rate"),
        ("What is the moratorium period for an education loan?", "moratorium"),
        ("What documents are needed for an education loan?", "documents"),
    ],
    "gold": [
        ("What is the interest rate for a gold loan?", "interest rate"),
        ("How is gold loan amount decided?", "amount"),
        ("What is the tenure for a gold loan?", "tenure"),
    ],
    "msme": [
        ("What is the interest rate for an MSME loan?", "interest rate"),
        ("What documents are needed for an MSME loan?", "documents"),
        ("What is the maximum amount for an MSME loan?", "amount"),
    ],
}


def emi(principal, annual_rate, months):
    r = annual_rate / 100.0 / 12.0
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def make_record(rng, i, year=None):
    key = rng.choice(list(LOAN_TYPES))
    label, lo, hi, rlo, rhi, tenures, purposes = LOAN_TYPES[key]
    # F016: prefer the seeded ranges / purposes / tenures from real
    # artifacts (terminology.yaml) when loaded; built-ins are the fallback.
    seed = (TERMINOLOGY.get("loan_types", {}).get(key, {})
            if TERMINOLOGY else {})
    if seed:
        try:
            rlo = float(seed.get("rate_min", rlo))
            rhi = float(seed.get("rate_max", rhi))
        except (TypeError, ValueError):
            pass
        seeded_purposes = _seed_texts(seed.get("purposes"))
        if seeded_purposes:
            purposes = seeded_purposes
        if seed.get("tenures"):
            tenures = list(seed["tenures"])
    # clustered amounts: log-uniform feels more realistic than uniform
    amount = int(math.exp(rng.uniform(math.log(lo), math.log(hi))) // 1000 * 1000)
    rate = round(rng.uniform(rlo, rhi), 2)
    tenure = rng.choice(tenures)
    monthly = emi(amount, rate, tenure)
    q, topic = rng.choice(QUESTIONS[key])
    channel = rng.choice(CHANNELS)
    name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    loan_id = f"LN{rng.randint(100000, 999999)}{i:06d}"[-12:]
    if year:
        # One year per run/shard: 200k records per annum. Start date is
        # inside that year, which is also the S3 yyyy/mm/dd partition.
        start = date(int(year), 1, 1) + timedelta(days=rng.randint(0, 364))
    else:
        start = date(2023, 1, 1) + timedelta(days=rng.randint(0, 900))
    # F018: the policy version in force for this loan type in the
    # record's start year (e.g. a 2024 home loan -> home-v2024-01).
    policy_version = policy_version_for_record(key, start.year)
    # F016: per-record seed picks (rng-driven, so determinism holds).
    # Distinct picks from each pool keep records from sharing wording.
    seed_terms = []
    seed_docs = []
    seed_fee = ""
    rate_basis = ""
    prepayment = ""
    amount_note = ""
    if seed:
        terms_pool = _seed_texts(seed.get("terms"))
        docs_pool = _seed_texts(seed.get("documents"))
        if terms_pool:
            seed_terms = rng.sample(terms_pool, min(3, len(terms_pool)))
        if docs_pool:
            seed_docs = rng.sample(docs_pool, min(4, len(docs_pool)))
        fees_pool = _seed_texts(seed.get("fees"))
        if fees_pool:
            seed_fee = rng.choice(fees_pool)
        rate_basis = str(seed.get("rate_basis", "") or "")
        prepayment = str(seed.get("prepayment", "") or "")
        amount_note = str(seed.get("amount_note", "") or "")
    rec = {
        "i": i, "loan_id": loan_id, "name": name, "type_key": key,
        "loan_type": label, "amount": amount, "rate": rate, "tenure": tenure,
        "emi": round(monthly, 2), "purpose": rng.choice(purposes),
        "branch": rng.choice(BRANCHES), "channel": channel,
        "status": rng.choice(["Approved", "Disbursed", "Under Review", "Approved"]),
        "start_date": start.isoformat(),
        "question": q, "topic": topic,
        "credit_score": rng.randint(650, 850),
        # F018: policy version in force for this loan type + start year.
        "policy_version": policy_version,
        # F016: longest tenure offered for this product, from the seeded
        # tenures when loaded (so the tenure answer matches the draw).
        "max_tenure": max(tenures),
        # Uniqueness: variant picks a paraphrase template + layout, so two
        # records with the same loan type do not share the same wording.
        "variant": rng.randint(0, 3),
        "layout": rng.randint(0, 2),
        # F016 seed fields (empty when terminology.yaml is not loaded).
        "seed_terms": seed_terms, "seed_documents": seed_docs,
        "seed_fee": seed_fee, "rate_basis": rate_basis,
        "seed_prepayment": prepayment, "seed_amount_note": amount_note,
    }
    # F019: hash of the business natural key (full content), so the
    # worker can claim the record atomically in the dedup table.
    rec["natural_hash"] = natural_hash_for_record(rec)
    return rec


# Four paraphrase variants per topic. Variant is chosen per record
# (rec["variant"]), so the same facts are expressed in different words.
def answer_for(rec):
    t = rec["topic"]
    v = rec.get("variant", 0)
    lt, amt, rate, ten, emi_v, lid = (rec["loan_type"], rec["amount"], rec["rate"],
                                      rec["tenure"], rec["emi"], rec["loan_id"])
    if t == "interest rate":
        # F016: rate basis comes from the seeds (e.g. "linked to the repo
        # rate", "linked to the 1-year MCLR") when terminology is loaded.
        basis = rec.get("rate_basis") or ""
        basis_txt = f" The rate is {basis}." if basis else ""
        return [
            f"The interest rate for a {lt} is {rate}% per annum. For loan {lid}, the sanctioned rate is {rate}% on Rs. {amt:,} over {ten} months.",
            f"Loan {lid} carries {rate}% a year.{basis_txt} That is the rate applied to the {lt} of Rs. {amt:,}, repayable over {ten} months.",
            f"For this {lt}, the bank charges {rate}% per annum. The sanctioned amount is Rs. {amt:,}, and the term is {ten} months.",
            f"At {rate}% per annum, this {lt} (loan {lid}) costs that rate on Rs. {amt:,}, across a {ten}-month term.{basis_txt}",
        ][v % 4]
    if t == "emi":
        return [
            f"EMI is calculated on the principal of Rs. {amt:,} at {rate}% per annum over {ten} months. The EMI for loan {lid} is Rs. {emi_v:,} per month.",
            f"With Rs. {amt:,} borrowed at {rate}% for {ten} months, the monthly instalment comes to Rs. {emi_v:,}. That is the EMI for loan {lid}.",
            f"For loan {lid}, the monthly payment is Rs. {emi_v:,}. It is based on Rs. {amt:,} at {rate}% a year, spread over {ten} months.",
            f"Repayment is Rs. {emi_v:,} a month. The calculation uses a principal of Rs. {amt:,}, a rate of {rate}%, and a {ten}-month tenure.",
        ][v % 4]
    if t == "tenure":
        # F016: max tenure comes from the record (seeded tenures when
        # loaded), not the built-in LOAN_TYPES list.
        max_ten = rec.get("max_tenure") or max(LOAN_TYPES[rec['type_key']][5])
        return [
            f"The tenure for this {lt} is {ten} months. Available tenures for {lt} range up to {max_ten} months.",
            f"This {lt} runs for {ten} months. The longest tenure offered for this product is {max_ten} months.",
            f"Loan {lid} is scheduled over {ten} months. Other tenures are available, up to {max_ten} months for a {lt}.",
            f"The agreed term is {ten} months — that is how long this {lt} takes to repay.",
        ][v % 4]
    if t == "documents":
        # F016: the document list is the rng-picked subset of the real
        # checklist for this loan type (seed_documents); each record
        # lists different documents, which also helps uniqueness.
        docs = rec.get("seed_documents") or []
        if docs:
            if len(docs) > 1:
                doc_list = ", ".join(docs[:-1]) + " and " + docs[-1]
            else:
                doc_list = docs[0]
            return [
                f"For a {lt}, please submit {doc_list}. Loan {lid} was processed at {rec['branch']} branch.",
                f"Loan {lid} needed {doc_list}. It was processed at {rec['branch']}.",
                f"To apply for this {lt}, the bank asks for {doc_list}. Processing for loan {lid} happened at {rec['branch']} branch.",
                f"The document set for loan {lid} is: {doc_list}.",
            ][v % 4]
        return [
            f"For a {lt}, please submit identity proof, address proof, income proof, bank statements for the last 6 months, and the completed application form. Loan {lid} was processed at {rec['branch']} branch.",
            f"Loan {lid} needed identity and address proof, proof of income, six months of bank statements, and a signed application form. It was processed at {rec['branch']}.",
            f"To apply for this {lt}, the bank asks for ID proof, address proof, income proof, and the last six months' statements. Processing for loan {lid} happened at {rec['branch']} branch.",
            f"The document set for loan {lid} is: identity proof, address proof, income proof, bank statements (6 months), and the application form.",
        ][v % 4]
    if t == "eligibility":
        return [
            f"Eligibility for a {lt} requires a credit score of 650 or above. The applicant for loan {lid} has a credit score of {rec['credit_score']}.",
            f"A score of 650 or higher is needed for this {lt}. This applicant scored {rec['credit_score']}, for loan {lid}.",
            f"Loan {lid}: the applicant's credit score is {rec['credit_score']}, which meets the 650 minimum for a {lt}.",
            f"For this {lt}, the bank looks for a credit score of at least 650. Here the score is {rec['credit_score']}.",
        ][v % 4]
    if t == "prepayment":
        # F016: the sourced prepayment term for this loan type, when the
        # seeds carry one (e.g. "No prepayment penalty on floating-rate
        # home loans"); otherwise the generic MITC wording below.
        prep = rec.get("seed_prepayment") or ""
        prep_txt = f" {prep}." if prep else ""
        return [
            f"Yes, the {lt} can be prepaid after 6 months.{prep_txt} Prepayment charges, if any, are as per the Most Important Terms and Conditions for loan {lid}.",
            f"Prepayment is allowed after six months on loan {lid}. Any charges follow the Most Important Terms and Conditions for this {lt}.",
            f"Loan {lid} can be closed early once six months have passed.{prep_txt} Check the MITC for any prepayment charge on this {lt}.",
            f"Yes — after 6 months, this {lt} may be prepaid in part or in full, subject to the charges in the MITC for loan {lid}.{prep_txt}",
        ][v % 4]
    if t == "amount":
        # F016: gold loans carry the sourced LTV / valuation note.
        note = rec.get("seed_amount_note") or ""
        note_txt = f" {note}." if note else ""
        return [
            f"The sanctioned amount for loan {lid} is Rs. {amt:,} for {rec['purpose']}. The maximum amount depends on income, credit score and collateral.",
            f"Loan {lid} was sanctioned for Rs. {amt:,}, to be used for {rec['purpose']}. How much a borrower can get depends on income, score and collateral.",
            f"Rs. {amt:,} is the amount sanctioned under loan {lid}. The purpose is {rec['purpose']}; the ceiling varies with income and credit history.{note_txt}",
            f"For {rec['purpose']}, the bank sanctioned Rs. {amt:,} on loan {lid}.",
        ][v % 4]
    if t == "moratorium":
        return [
            f"The moratorium period for an education loan is the course period plus 6 to 12 months. For loan {lid}, repayment starts after the moratorium period.",
            f"Repayment on loan {lid} begins after the moratorium — the course period plus six to twelve months. Simple interest is charged during the moratorium period.",
            f"For this education loan, there is no repayment during the course, plus a further 6 to 12 months. Loan {lid} follows that schedule.",
            f"The moratorium for loan {lid} covers the study period and 6–12 months after it, before EMI starts.",
        ][v % 4]
    return f"Loan {lid}: {lt} of Rs. {amt:,} at {rate}% for {ten} months."


def _context_line(rec):
    """One unique contextual sentence per record, from channel / purpose / status."""
    v = rec.get("variant", 0)
    terms = rec.get("seed_terms") or []
    if terms:
        # F016: one of the record's seed terms, so real terminology
        # appears in the summary body as well as the answer.
        term_line = f"The sanction letter for this {rec['loan_type']} records {terms[0]}."
    else:
        term_line = f"Servicing branch is {rec['branch']}. The request arrived via {rec['channel']}."
    templates = [
        f"This loan came in through the {rec['channel']} channel, handled at {rec['branch']}.",
        f"The application for {rec['purpose']} was processed at {rec['branch']} and is now {rec['status'].lower()}.",
        f"Requested for {rec['purpose']}, this {rec['loan_type']} is currently {rec['status'].lower()}.",
        term_line,
    ]
    return templates[v % 4]


def lines_for(rec):
    a = answer_for(rec)
    v = rec.get("variant", 0)
    layout = rec.get("layout", 0)
    # Varied field labels per variant, so the summary lines themselves differ.
    amount_label = ["Amount", "Sanctioned amount", "Loan amount", "Principal"][v % 4]
    emi_label = ["EMI", "Monthly instalment", "EMI per month", "Monthly payment"][v % 4]
    rate_label = ["Interest Rate", "Rate charged", "Interest rate", "Rate per annum"][v % 4]
    fields = [
        f"{rec['loan_type']} — Loan Summary",
        f"Loan ID: {rec['loan_id']}",
        f"Customer: {rec['name']}",
        f"Loan Type: {rec['loan_type']}",
        f"Purpose: {rec['purpose']}",
        f"{amount_label}: Rs. {rec['amount']:,}",
        f"{rate_label}: {rec['rate']}% per annum",
        f"Tenure: {rec['tenure']} months",
        f"{emi_label}: Rs. {rec['emi']:,} per month",
        f"Credit Score: {rec['credit_score']}",
        f"Status: {rec['status']}",
        f"Branch: {rec['branch']}",
        f"Start Date: {rec['start_date']}",
        f"Channel: {rec['channel']}",
        _context_line(rec),
    ]
    # F018: policy version in force (index 15). Records built before
    # F018 have no such field; guard so lines_for stays total.
    if rec.get("policy_version"):
        fields.append(f"Policy Version: {rec['policy_version']}")
    # F016: the record's seed terms, so every document carries real
    # terminology from the seeds. Appended after `fields` so the layout-2
    # reorder above (fields[0..15]) is unaffected.
    seed_line = []
    if rec.get("seed_terms"):
        seed_line = [f"Key terms: {', '.join(rec['seed_terms'])}."]
    if layout == 1:
        # Question-first layout.
        return [f"Question: {rec['question']}", f"Answer: {a}", ""] + fields + seed_line + [
            "", "Note: This is a synthetic document generated for RAG testing. All names and IDs are fictional."]
    if layout == 2:
        # Status-first layout, fields in a different order. Index 15 is
        # the F018 policy-version line; it is skipped for records that
        # predate it (fields then has only 15 entries).
        order = [0, 10, 11, 1, 2, 5, 6, 7, 8, 3, 4, 9, 12, 13, 14, 15]
        reordered = [fields[i] for i in order if i < len(fields)]
        return reordered + seed_line + ["", f"Question: {rec['question']}", f"Answer: {a}",
                            "", "Note: This is a synthetic document generated for RAG testing. All names and IDs are fictional."]
    return fields + seed_line + ["", f"Question: {rec['question']}", f"Answer: {a}",
                     "", "Note: This is a synthetic document generated for RAG testing. All names and IDs are fictional."]


# ---------------------------------------------------------------- writers

def write_txt(path, rec, lines=None):
    # F018: `lines` lets the policy generator reuse this writer for
    # rule-shaped documents (rec is None there).
    if lines is None:
        lines = lines_for(rec)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path, rec):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["loan_id", "customer", "loan_type", "purpose", "amount_inr",
                    "interest_rate_pct", "tenure_months", "emi_inr", "credit_score",
                    "status", "branch", "start_date", "channel", "question", "answer"])
        w.writerow([rec["loan_id"], rec["name"], rec["loan_type"], rec["purpose"],
                    rec["amount"], rec["rate"], rec["tenure"], rec["emi"],
                    rec["credit_score"], rec["status"], rec["branch"],
                    rec["start_date"], rec["channel"], rec["question"], answer_for(rec)])


def _xml_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def write_docx(path, rec, lines=None):
    # F018: `lines` override, see write_txt.
    if lines is None:
        lines = lines_for(rec)
    paras = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{_xml_escape(line)}</w:t></w:r></w:p>"
        for line in lines)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{paras}</w:body></w:document>")
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)


def write_xlsx(path, rec):
    rows = [
        ("Loan ID", rec["loan_id"]), ("Customer", rec["name"]),
        ("Loan Type", rec["loan_type"]), ("Purpose", rec["purpose"]),
        ("Amount (INR)", rec["amount"]), ("Interest Rate (%)", rec["rate"]),
        ("Tenure (months)", rec["tenure"]), ("EMI (INR)", rec["emi"]),
        ("Credit Score", rec["credit_score"]), ("Status", rec["status"]),
        ("Branch", rec["branch"]), ("Start Date", rec["start_date"]),
        ("Channel", rec["channel"]), ("Question", rec["question"]),
        ("Answer", answer_for(rec)),
    ]
    # EMI schedule (first 12 months) as a second block
    sched = [("Month", "EMI (INR)", "Principal (INR)", "Interest (INR)", "Balance (INR)")]
    bal, r = float(rec["amount"]), rec["rate"] / 100.0 / 12.0
    for m in range(1, 13):
        interest = bal * r
        principal = rec["emi"] - interest
        bal = max(0.0, bal - principal)
        sched.append((m, round(rec["emi"], 2), round(principal, 2), round(interest, 2), round(bal, 2)))

    def sheet_xml(data, header=None):
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
        all_rows = ([header] + data) if header else data
        for ri, row in enumerate(all_rows, 1):
            out.append(f"<row r=\"{ri}\">")
            for ci, v in enumerate(row, 1):
                col = chr(64 + ci) if ci <= 26 else "A" + chr(64 + ci - 26)
                if isinstance(v, (int, float)):
                    out.append(f"<c r=\"{col}{ri}\"><v>{v}</v></c>")
                else:
                    out.append(f"<c r=\"{col}{ri}\" t=\"inlineStr\"><is><t>{_xml_escape(v)}</t></is></c>")
            out.append("</row>")
        out.append("</sheetData></worksheet>")
        return "".join(out)

    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="Loan" sheetId="1" r:id="rId1"/>'
          '<sheet name="EMI Schedule" sheetId="2" r:id="rId2"/></sheets></workbook>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
          '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
          "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>")
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
               '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
               "</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml([(k, v) for k, v in rows], header=("Field", "Value")))
        z.writestr("xl/worksheets/sheet2.xml", sheet_xml(sched[1:], header=sched[0]))


def _pdf_escape(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path, rec, lines=None):
    # F018: `lines` override, see write_txt.
    if lines is None:
        lines = lines_for(rec)
    content = ["BT /F1 11 Tf 50 780 Td"]
    y = 780
    for line in lines:
        if line == "":
            y -= 12
            continue
        # wrap long lines at ~95 chars
        while len(line) > 95:
            chunk, line = line[:95], line[95:]
            content.append(f"({_pdf_escape(chunk)}) Tj 0 -14 Td")
            y -= 14
        content.append(f"({_pdf_escape(line)}) Tj 0 -14 Td")
        y -= 14
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")
    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    path.write_bytes(bytes(out))


def write_png(path, rec, lines=None, title=None):
    # F018: `lines`/`title` override lets the policy generator reuse
    # this writer (rec is None there, so no question line is drawn).
    if lines is None:
        lines = lines_for(rec)
    if title is None:
        title = f"{rec['loan_type']} — Loan Summary"
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        # Plain PNG fallback (valid image, no text) — install Pillow for real cards
        w, h = 800, 500
        raw = b"".join(b"\x00" + bytes([240, 244, 248]) * w for _ in range(h))
        def chunk(typ, data):
            c = struct.pack(">I", len(data)) + typ + data
            return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw))
               + chunk(b"IEND", b""))
        path.write_bytes(png)
        return
    img = Image.new("RGB", (900, 560), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 70], fill=(18, 60, 110))
    d.text((30, 22), title, fill="white")
    y = 100
    for line in lines[1:14]:
        d.text((30, y), line, fill=(20, 20, 20))
        y += 30
    if rec is not None:
        d.text((30, y + 10), f"Q: {rec['question']}", fill=(18, 60, 110))
    img.save(path, "PNG")


WRITERS = {
    "pdf": ("pdf", write_pdf), "docx": ("docx", write_docx),
    "xlsx": ("xlsx", write_xlsx), "csv": ("csv", write_csv),
    "txt": ("txt", write_txt), "png": ("png", write_png),
}


def description_shingles(rec, n=5):
    """Word 5-gram shingles of the description, numbers stripped.

    This is the wording-only overlap measure: two descriptions that differ
    only in amounts/names will have near-identical shingle sets.
    """
    text = "\n".join(lines_for(rec))
    words = re.findall(r"[a-z]+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def max_overlap(shingles, kept, sample=50, rng=None):
    """Max Jaccard vs a random sample of already-kept shingle sets."""
    if not kept:
        return 0.0
    pool = kept if len(kept) <= sample else (rng or random).sample(kept, sample)
    best = 0.0
    for other in pool:
        if not other:
            continue
        v = len(shingles & other) / len(shingles | other)
        if v > best:
            best = v
    return best

# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Generate banking loan RAG corpus, 1M per format if needed.")
    ap.add_argument("--count", type=int, default=10, help="documents per format")
    ap.add_argument("--out", type=Path, default=Path("./corpus"), help="output directory")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--formats", default="pdf,docx,xlsx,csv,txt,png",
                    help="comma-separated subset of pdf,docx,xlsx,csv,txt,png")
    ap.add_argument("--start", type=int, default=0, help="starting index (for sharding / resume)")
    ap.add_argument("--max-overlap", type=float, default=0.65,
                    help="reject a description if its wording-only 5-gram Jaccard vs kept descriptions exceeds this (default 0.65; 0 disables the check)")
    ap.add_argument("--year", type=int, default=None,
                    help="loan year for this run, e.g. 2024. Start dates fall inside that year (S3 yyyy/mm/dd partition).")
    args = ap.parse_args()
    formats = [f.strip() for f in args.formats.split(",") if f.strip() in WRITERS]
    if not formats:
        print("No valid formats. Choose from pdf,docx,xlsx,csv,txt,png", file=sys.stderr)
        return 2
    rng = random.Random(args.seed)
    # advance RNG deterministically past --start records so shards don't overlap
    for _ in range(args.start):
        make_record(rng, 0, year=args.year)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.jsonl"
    kept_shingles, rejected = [], 0
    with open(manifest_path, "a", encoding="utf-8") as mf:
        for idx in range(args.start, args.start + args.count):
            rec = make_record(rng, idx, year=args.year)
            if args.max_overlap > 0:
                # Generate -> measure -> reject/regenerate loop.
                for _attempt in range(5):
                    sh = description_shingles(rec)
                    if max_overlap(sh, kept_shingles, rng=rng) <= args.max_overlap:
                        break
                    rejected += 1
                    rec = make_record(rng, idx, year=args.year)
                    rec["variant"] = (rec.get("variant", 0) + 1) % 4
                    rec["layout"] = (rec.get("layout", 0) + 1) % 3
                else:
                    sh = description_shingles(rec)
                kept_shingles.append(description_shingles(rec))
            ans = answer_for(rec)
            for fmt in formats:
                ext, writer = WRITERS[fmt]
                sub = args.out / fmt
                sub.mkdir(exist_ok=True)
                fname = f"loan_{idx:07d}_{rec['loan_id']}.{ext}"
                writer(sub / fname, rec)
                mf.write(json.dumps({
                    "doc_id": f"{fmt}_{idx:07d}", "format": fmt, "file": f"{fmt}/{fname}",
                    "loan_id": rec["loan_id"], "loan_type": rec["loan_type"],
                    "channel": rec["channel"], "question": rec["question"],
                    "answer": ans,
                    "policy_version": rec["policy_version"],
                    "natural_hash": rec["natural_hash"],
                }) + "\n")
            if (idx - args.start + 1) % 1000 == 0:
                print(f"  ... {idx - args.start + 1}/{args.count} records done", flush=True)
    total_files = args.count * len(formats)
    print(f"Done: {args.count} records x {len(formats)} formats = {total_files} files in {args.out}")
    print(f"Uniqueness: {rejected} description(s) rejected/regenerated for overlap > {args.max_overlap}")
    print(f"Manifest: {manifest_path}")
    print("Scale note: 1,000,000 per format = 6,000,000 files. Test ingestion at 1k first, then scale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
