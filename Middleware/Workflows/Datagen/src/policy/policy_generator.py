#!/usr/bin/env python3
"""
F018 — Policy corpus generator (small, versioned).

One document = one rule that applies to thousands of loans
(DESIGN.md §3.2). The corpus is SMALL and fixed: 2 versions per loan
type x 7 loan types, each version holding the rule topics that exist
for that type. That is tens of documents, not millions — 200k copies
of the same policy would be duplicate content that drowns retrieval.

    python3 src/policy/policy_generator.py --out ./policy-corpus
    python3 src/policy/policy_generator.py --out ./policy-corpus --formats txt

Output: out/policy/<loan_type>/version=<version>/policy_<policy_id>.<ext>
plus out/policy/manifest.jsonl (record_kind: policy).

Rule text comes from data/seeds/terminology.yaml (F016 seeds) wherever
possible: rate ranges + basis, prepayment terms, document checklists,
fees, tenures, gold LTV caps. Every rule carries the seed IDs it
traces to. A rule that cannot be traced to a fetched seed is OMITTED,
not invented — see data/policies/POLICIES.md for what is missing and
why (e.g. business and MSME have no sourced prepayment rule; auto has
no sourced fees list).

Deterministic: the policy set is fixed, no randomness. --seed is
accepted for CLI parity with the customer generator and ignored.

No external dependencies. The 6 formats reuse the customer
generator's writers (TXT/PDF/DOCX/PNG via the `lines` override) and
small policy-specific CSV/XLSX writers in this file.
"""
import argparse
import csv
import json
import sys
import zipfile
from pathlib import Path

# src/ on the path so this works both as a script
# (python3 src/policy/policy_generator.py) and as an import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generator.generator import (  # noqa: E402
    TERMINOLOGY, _seed_texts, _xml_escape, load_terminology,
    write_docx, write_pdf, write_png, write_txt,
)
from policy.versions import (  # noqa: E402
    POLICY_VERSIONS, is_latest, supersedes,
)

TOPIC_LABELS = {
    "interest-rate": "Interest rate",
    "prepayment": "Prepayment",
    "documents": "Documents required",
    "fees": "Fees and charges",
    "tenure": "Tenure",
    "ltv": "Loan to value (LTV)",
}
# Topics in the order they appear in each policy version's documents.
TOPIC_ORDER = ["interest-rate", "prepayment", "documents", "fees",
               "tenure", "ltv"]


def _fmt_num(value):
    """Rate figures without trailing noise: 24.0 -> '24', 7.4 -> '7.4'."""
    return f"{float(value):g}"


def _unique(seq):
    out = []
    for item in seq:
        if item not in out:
            out.append(item)
    return out


def _prepayment_source(seed):
    """Seed ID for the prepayment rule, or None if it cannot be traced.

    The prepayment sentence in terminology.yaml carries no source of
    its own, so trace it: first a fees entry with the same text, else
    a document entry named in the sentence (auto: 'prepayment
    statement'). No match means the rule is omitted, not guessed.
    """
    prep = (seed.get("prepayment") or "").strip()
    if not prep:
        return None
    for entry in seed.get("fees") or []:
        if isinstance(entry, dict) and entry.get("text", "").strip().lower() == prep.lower():
            return entry.get("source")
    for entry in seed.get("documents") or []:
        if isinstance(entry, dict) and entry.get("text", "").strip().lower() in prep.lower():
            return entry.get("source")
    return None


def _rule_for_topic(key, seed):
    """(rule text, [seed IDs]) for one topic, or None if unsourceable.

    Returns None when the topic has no sourced material for this loan
    type (business/MSME prepayment, auto fees) — the caller omits it.
    """
    label = seed["label"]
    if key == "interest-rate":
        lo = _fmt_num(seed["rate_min"])
        hi = _fmt_num(seed["rate_max"])
        basis = str(seed.get("rate_basis") or "").strip()
        note = str(seed.get("rate_note") or "").strip()
        if basis:
            rule = (f"The interest rate for a {label} is {lo}% to {hi}% "
                    f"per annum, {basis}. {note}")
        else:
            rule = (f"The interest rate for a {label} ranges from {lo}% "
                    f"to {hi}% per annum. {note}")
        return rule, list(seed.get("rate_sources") or [])
    if key == "prepayment":
        prep = (seed.get("prepayment") or "").strip()
        src = _prepayment_source(seed)
        if not prep or not src:
            return None
        return f"Prepayment rule for {label}: {prep}.", [src]
    if key == "documents":
        docs = _seed_texts(seed.get("documents"))
        if not docs:
            return None
        if len(docs) > 1:
            doc_list = ", ".join(docs[:-1]) + " and " + docs[-1]
        else:
            doc_list = docs[0]
        sources = _unique(e.get("source") for e in seed.get("documents") or []
                          if isinstance(e, dict) and e.get("source"))
        return f"To apply for a {label}, the bank asks for: {doc_list}.", sources
    if key == "fees":
        fees = _seed_texts(seed.get("fees"))
        if not fees:
            return None
        sources = _unique(e.get("source") for e in seed.get("fees") or []
                          if isinstance(e, dict) and e.get("source"))
        return f"Fees and charges for a {label}: {'; '.join(fees)}.", sources
    if key == "tenure":
        tenures = list(seed.get("tenures") or [])
        if not tenures:
            return None
        # Tenure bands carry no per-entry source in terminology.yaml;
        # they come from the same lender pages as the rate ranges.
        return (f"Available tenures for a {label}: "
                f"{', '.join(str(t) for t in tenures)} months "
                f"(up to {max(tenures)} months)."), list(seed.get("rate_sources") or [])
    if key == "ltv":
        note = str(seed.get("amount_note") or "").strip()
        if not note:
            return None
        # amount_note is the RBI gold-directions valuation/LTV text
        # (SEEDS.md RBI-GOLD-01: LTV caps 85/80/75, IBJA valuation).
        return note + ".", ["RBI-GOLD-01"]
    return None


def build_policies(terminology=None):
    """The full fixed policy set: one dict per (loan type, version, topic).

    Deterministic order: loan types as listed in terminology.yaml,
    versions oldest first, topics in TOPIC_ORDER.
    """
    term = terminology if terminology is not None else TERMINOLOGY
    if not term:
        term = load_terminology()
    policies = []
    for key, seed in term.get("loan_types", {}).items():
        for version, eff in POLICY_VERSIONS[key]:
            version_id = f"{key}-{version}"
            for topic in TOPIC_ORDER:
                built = _rule_for_topic(topic, seed)
                if built is None:
                    continue
                rule, sources = built
                policies.append({
                    "policy_id": f"{version_id}-{topic}",
                    "loan_type": key,
                    "loan_label": seed["label"],
                    "version": version_id,
                    "version_short": version,
                    "effective_date": eff,
                    "supersedes": supersedes(key, version),
                    "latest": is_latest(key, version),
                    "topic": topic,
                    "topic_label": TOPIC_LABELS[topic],
                    "rule": rule,
                    "sources": sources,
                })
    return policies


def lines_for_policy(policy):
    """Description lines for one policy document (all 6 formats)."""
    sup = policy["supersedes"] or "none (first version)"
    return [
        f"{policy['loan_label']} — Policy {policy['version']}: {policy['topic_label']}",
        f"Policy ID: {policy['policy_id']}",
        f"Loan Type: {policy['loan_label']}",
        f"Version: {policy['version']}",
        f"Effective Date: {policy['effective_date']}",
        f"Supersedes: {sup}",
        f"Latest: {'yes' if policy['latest'] else 'no'}",
        f"Rule Topic: {policy['topic_label']}",
        f"Rule: {policy['rule']}",
        f"Sources: {', '.join(policy['sources'])}",
        "",
        "Note: This is a synthetic policy document generated for RAG testing. "
        "Rule text is drawn from the public sources listed in data/seeds/SEEDS.md.",
    ]


def write_policy_csv(path, policy):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["policy_id", "loan_type", "version", "effective_date",
                    "supersedes", "latest", "topic", "rule", "sources"])
        w.writerow([policy["policy_id"], policy["loan_label"],
                    policy["version"], policy["effective_date"],
                    policy["supersedes"] or "",
                    "yes" if policy["latest"] else "no",
                    policy["topic_label"], policy["rule"],
                    ", ".join(policy["sources"])])


def _xlsx_sheet_xml(rows, header):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for ri, row in enumerate([header] + rows, 1):
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


def write_policy_xlsx(path, policy):
    rows = [
        ("Policy ID", policy["policy_id"]),
        ("Loan Type", policy["loan_label"]),
        ("Version", policy["version"]),
        ("Effective Date", policy["effective_date"]),
        ("Supersedes", policy["supersedes"] or "none (first version)"),
        ("Latest", "yes" if policy["latest"] else "no"),
        ("Rule Topic", policy["topic_label"]),
        ("Rule", policy["rule"]),
        ("Sources", ", ".join(policy["sources"])),
    ]
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="Policy" sheetId="1" r:id="rId1"/></sheets></workbook>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
          "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>")
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
               "</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml",
                   _xlsx_sheet_xml(rows, header=("Field", "Value")))


WRITERS = {
    "pdf": ("pdf", lambda p, pol, lines: write_pdf(p, None, lines=lines)),
    "docx": ("docx", lambda p, pol, lines: write_docx(p, None, lines=lines)),
    "xlsx": ("xlsx", write_policy_xlsx),
    "csv": ("csv", write_policy_csv),
    "txt": ("txt", lambda p, pol, lines: write_txt(p, None, lines=lines)),
    "png": ("png", lambda p, pol, lines: write_png(p, None, lines=lines, title=lines[0])),
}


def main():
    ap = argparse.ArgumentParser(
        description="Generate the small versioned policy corpus (F018).")
    ap.add_argument("--out", type=Path, default=Path("./policy-corpus"),
                    help="output directory (policy docs land in <out>/policy/)")
    ap.add_argument("--seed", type=int, default=7,
                    help="accepted for parity with the customer generator; "
                         "the policy set is fixed, so the seed changes nothing")
    ap.add_argument("--formats", default="pdf,docx,xlsx,csv,txt,png",
                    help="comma-separated subset of pdf,docx,xlsx,csv,txt,png")
    args = ap.parse_args()
    formats = [f.strip() for f in args.formats.split(",") if f.strip() in WRITERS]
    if not formats:
        print("No valid formats. Choose from pdf,docx,xlsx,csv,txt,png",
              file=sys.stderr)
        return 2
    policies = build_policies()
    out = args.out / "policy"
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.jsonl"
    with open(manifest_path, "w", encoding="utf-8") as mf:
        for pol in policies:
            lines = lines_for_policy(pol)
            for fmt in formats:
                ext, writer = WRITERS[fmt]
                sub = out / pol["loan_type"] / f"version={pol['version_short']}"
                sub.mkdir(parents=True, exist_ok=True)
                fname = f"policy_{pol['policy_id']}.{ext}"
                if fmt in ("xlsx", "csv"):
                    writer(sub / fname, pol)
                else:
                    writer(sub / fname, pol, lines)
                mf.write(json.dumps({
                    "doc_id": f"policy_{pol['policy_id']}",
                    "record_kind": "policy",
                    "format": fmt,
                    "file": f"{pol['loan_type']}/version={pol['version_short']}/{fname}",
                    "loan_type": pol["loan_label"],
                    "policy_id": pol["policy_id"],
                    "policy_version": pol["version"],
                    "effective_date": pol["effective_date"],
                    "supersedes": pol["supersedes"],
                    "latest": pol["latest"],
                    "topic": pol["topic"],
                    "sources": pol["sources"],
                }) + "\n")
    total_files = len(policies) * len(formats)
    print(f"Done: {len(policies)} policy documents x {len(formats)} formats "
          f"= {total_files} files in {out}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
