#!/usr/bin/env python3
"""Close the issues whose work is already done and verified in the repo.

Kishore approved closing 57 issues on 2026-11-12 (M001 complete,
M002 complete, E004 + F017 in M003). Kishore approved closing
F016 + S036-S038 on 2026-11-12 (real-artifact seeding, 6 commits,
HEAD bc5bab8, CI green). The list below is explicit:
issue ID -> GitHub issue number, verified against the live repo
before this script was written. Do not close anything else.

Evidence per group (also posted as the closing comment on each issue):
- E001 / F001-F003 / S001-S008: generator core in
  src/generator/generator.py — deterministic, 7 loan types, EMI
  computed, CLI --seed/--start/--count/--formats.
- E002 / F004-F009 / S009-S020: all six writers in
  src/generator/generator.py; 10 records x 6 formats verified,
  PDF/DOCX/XLSX parse correctly.
- E003 / F010-F012 / S021-S026: manifest.jsonl with Q&A, S3 keys
  raw/<format>/year=.../month=.../day=.../ by loan start date,
  --year flag in generator and planner.
- E004 / F013-F015 / S027-S035: uniqueness_check.py (wording-only
  5-gram Jaccard) + uniqueness_report.md; v2 wording-only mean
  0.128, same-type pairs >0.5 down to 1.5% on 200 records;
  --max-overlap 0.65 reject/regenerate loop in the generator.
- F017 / S039-S040: log-uniform amounts and realistic rate /
  tenure / credit-score ranges per loan type in
  src/generator/generator.py.
- F016 / S036-S038: real-artifact seeding — data/seeds/SEEDS.md
  (21 fetched public artifacts), data/seeds/terminology.yaml
  (551 lines, sourced rates/checklists/terms per loan type),
  generator.py loads it at runtime (PyYAML or built-in parser)
  and picks seed terms/documents/fees per record, Dockerfile
  copies data/seeds/ into the worker image; 11/11 tests pass,
  uniqueness wording-only mean 0.109.

Idempotent: already-closed issues are skipped, not re-commented.
Run via the manual "Close Issues (manual)" workflow, which uses
the repo's own GITHUB_TOKEN — no per-issue approvals.
"""
import json
import os
import sys
import urllib.request

EVIDENCE = {
    "core": "Verified done: generator core in src/generator/generator.py — deterministic, 7 loan types, EMI computed from amount/rate/tenure, CLI --seed / --start / --count / --formats. M001 complete.",
    "formats": "Verified done: all six writers in src/generator/generator.py; 10 records x 6 formats verified, PDF/DOCX/XLSX parse correctly. M002 complete.",
    "manifest": "Verified done: manifest.jsonl with question + answer per file, S3 keys raw/<format>/year=YYYY/month=MM/day=DD/ by loan start date, --year flag in generator and planner. M002 complete.",
    "uniqueness": "Verified done: uniqueness_check.py (wording-only 5-gram Jaccard) + uniqueness_report.md; v2 wording-only mean 0.128, same-type pairs >0.5 down to 1.5% on 200 records; --max-overlap 0.65 reject/regenerate loop.",
    "realism": "Verified done: log-uniform amounts and realistic rate / tenure / credit-score ranges per loan type in src/generator/generator.py.",
    "f016": "Verified done: real-artifact seeding — data/seeds/SEEDS.md (21 fetched public artifacts), data/seeds/terminology.yaml (551 lines, sourced rates/checklists/terms per loan type), generator.py loads it at runtime and picks seed terms/documents/fees per record, Dockerfile copies data/seeds/ into the worker image; 11/11 tests pass, uniqueness wording-only mean 0.109. F016 complete.",
}

# (issue id, GitHub issue number, evidence group)
CLOSE = (
    [("E001", 1, "core"),
     ("F001", 10, "core"), ("F002", 14, "core"), ("F003", 18, "core"),
     ("S001", 11, "core"), ("S002", 12, "core"), ("S003", 13, "core"),
     ("S004", 15, "core"), ("S005", 16, "core"), ("S006", 17, "core"),
     ("S007", 19, "core"), ("S008", 20, "core")]
    + [("E002", 2, "formats"),
       ("F004", 21, "formats"), ("F005", 24, "formats"),
       ("F006", 27, "formats"), ("F007", 30, "formats"),
       ("F008", 33, "formats"), ("F009", 36, "formats"),
       ("S009", 22, "formats"), ("S010", 23, "formats"),
       ("S011", 25, "formats"), ("S012", 26, "formats"),
       ("S013", 28, "formats"), ("S014", 29, "formats"),
       ("S015", 31, "formats"), ("S016", 32, "formats"),
       ("S017", 34, "formats"), ("S018", 35, "formats"),
       ("S019", 37, "formats"), ("S020", 38, "formats")]
    + [("E003", 3, "manifest"),
       ("F010", 39, "manifest"), ("F011", 42, "manifest"),
       ("F012", 45, "manifest"),
       ("S021", 40, "manifest"), ("S022", 41, "manifest"),
       ("S023", 43, "manifest"), ("S024", 44, "manifest"),
       ("S025", 46, "manifest"), ("S026", 47, "manifest")]
    + [("E004", 4, "uniqueness"),
       ("F013", 48, "uniqueness"), ("F014", 52, "uniqueness"),
       ("F015", 56, "uniqueness"),
       ("S027", 49, "uniqueness"), ("S028", 50, "uniqueness"),
       ("S029", 51, "uniqueness"), ("S030", 53, "uniqueness"),
       ("S031", 54, "uniqueness"), ("S032", 55, "uniqueness"),
       ("S033", 57, "uniqueness"), ("S034", 58, "uniqueness"),
       ("S035", 59, "uniqueness")]
    + [("F017", 64, "realism"), ("S039", 65, "realism"),
       ("S040", 66, "realism")]
    + [("F016", 60, "f016"), ("S036", 61, "f016"),
       ("S037", 62, "f016"), ("S038", 63, "f016")]
)


def api(method, path, payload=None):
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ.get("GH_REPO", "javakishore-veleti/RAG-Banking-Loan-Data-Generators")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def main():
    assert len(CLOSE) == 61, f"expected 61 issues to close, got {len(CLOSE)}"
    closed = skipped = failed = 0
    for issue_id, number, group in CLOSE:
        try:
            _, issue = api("GET", f"/issues/{number}")
            title = issue.get("title", "")
            if issue_id not in title:
                print(f"ABORT: #{number} is not {issue_id} (title: {title})")
                return 1
            if issue.get("state") == "closed":
                print(f"Skip (already closed): #{number} {issue_id}")
                skipped += 1
                continue
            api("POST", f"/issues/{number}/comments",
                {"body": EVIDENCE[group]})
            api("PATCH", f"/issues/{number}", {"state": "closed"})
            print(f"Closed: #{number} {issue_id}")
            closed += 1
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"FAILED: #{number} {issue_id}: {exc}")
            failed += 1
    print(f"Done. Closed: {closed}, already closed: {skipped}, "
          f"failed: {failed}, total in list: {len(CLOSE)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
