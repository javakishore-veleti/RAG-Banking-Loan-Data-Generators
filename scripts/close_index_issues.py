#!/usr/bin/env python3
"""Close the indexing issues whose work is already done and verified
in the repo — the status updates as the code progresses.

The list below is explicit: issue ID -> evidence group. Unlike
scripts/close_issues.py (Datagen), the GitHub issue numbers are NOT
hard-coded here: they are resolved at run time by matching the issue
title prefix ("[Epic] E010 — ...", "[Feature] F034 — ...",
"[Story] S086 — ..."), because the creation order from
create-index-issues.yml is not guaranteed. The prefix match is the
safety check — an ID that matches no open issue is reported as
FAILED and counted, never closed blind.

Evidence per group (also posted as the closing comment on each issue):
- core: loader/chunker/enricher in
  Middleware/Workflows/DataIndexing/src/indexer/ (loader.py,
  chunker.py, enricher.py); deterministic chunk ids
  sha1(doc_id:chunk_index:model_slug); latest flag = newest version
  per loan; 8 unit tests pass; run_local.sh L0–L2 dry-run passes.
- config: config/embedding_models.yaml — default
  amazon.titan-embed-text-v2:0, per-format overrides null = default;
  resolution workflow input -> per-format override -> default;
  dimensions table + probe_dimensions; unit tests pass.
- testing: 8 unit tests in Middleware/Workflows/DataIndexing/tests/
  pass; run_local.sh dry-run (tests + L0–L2) passes with no AWS.
- docs: README §15, ARCHITECTURE §15, DESIGN §16 + decision log;
  CI runs indexer tests + py_compile (only close after the push
  shows CI green).

Do NOT add other issue IDs without Kishore approving them — closing
is the status change itself. The remaining indexing issues stay open
until their AWS-dependent work is verified: F037 (live Bedrock),
F039/F040 (live pgvector/OpenSearch), F041–F044 (planner, worker,
workflows, retry — need an AWS index run), S118 (golden-set
retrieval check), E011–E014 (their features are not all done).
"""
import json
import os
import sys
import urllib.request

EVIDENCE = {
    "core": "Verified done: loader/chunker/enricher in Middleware/Workflows/DataIndexing/src/indexer/ (loader.py, chunker.py, enricher.py) — per-format text extraction (PNG falls back to manifest description), recursive 500/100 chunking, metadata enrichment with latest flag and deterministic chunk ids sha1(doc_id:chunk_index:model_slug). 8 unit tests pass; run_local.sh L0–L2 dry-run passes with no AWS.",
    "config": "Verified done: config/embedding_models.yaml — default amazon.titan-embed-text-v2:0, per-format overrides null = default; resolution workflow input -> per-format override -> default; dimensions table + probe_dimensions. Unit tests pass.",
    "testing": "Verified done: 8 unit tests in Middleware/Workflows/DataIndexing/tests/ pass, and run_local.sh dry-run (tests + L0–L2 load/chunk/enrich) passes with no AWS.",
    "docs": "Verified done: README §15, ARCHITECTURE §15, DESIGN §16 + decision log updated; CI runs indexer tests + py_compile; GITHUB_ISSUES_INDEXING.md plan + create-index-issues workflow in repo.",
}

# (issue id, evidence group) — resolved by title prefix at run time.
CLOSE = (
    [("E010", "core"),
     ("F034", "core"), ("F035", "core"), ("F036", "core"),
     ("S086", "core"), ("S087", "core"), ("S088", "core"),
     ("S089", "core"), ("S090", "core"),
     ("S091", "core"), ("S092", "core"), ("S093", "core")]
    + [("F038", "config"),
       ("S097", "config"), ("S098", "config"), ("S099", "config")]
    + [("S116", "testing"), ("S117", "testing")]
    + [("F046", "docs"), ("S119", "docs"), ("S120", "docs")]
)

TYPE_PREFIX = {"E": "Epic", "F": "Feature", "S": "Story"}


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
    assert len(CLOSE) == 21, f"expected 21 issues to close, got {len(CLOSE)}"
    # Resolve every issue by title prefix first (state=all, paged).
    by_title = {}
    page = 1
    while True:
        _, issues = api("GET", f"/issues?state=all&per_page=100&page={page}")
        if not isinstance(issues, list) or not issues:
            break
        for issue in issues:
            by_title[issue["title"]] = issue
        if len(issues) < 100:
            break
        page += 1
    print(f"Issues in repo: {len(by_title)}")

    closed = skipped = failed = 0
    for issue_id, group in CLOSE:
        prefix = f"[{TYPE_PREFIX[issue_id[0]]}] {issue_id} — "
        match = next((i for t, i in by_title.items()
                      if t.startswith(prefix)), None)
        if match is None:
            print(f"FAILED: {issue_id} — no issue with title prefix {prefix!r}")
            failed += 1
            continue
        number = match["number"]
        try:
            if match.get("state") == "closed":
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
