#!/usr/bin/env python3
"""Close milestones whose issues are all closed.

Run only after the Close Issues workflow has finished and the
counts have been verified (M001: 12/12 closed, M002: 29/29 closed).
The script refuses to close a milestone that still has open
issues — it looks milestones up by title, so it does not depend
on milestone numbers. Idempotent: already-closed milestones are
skipped. Run via the manual "Close Milestones (manual)" workflow
with the repo's own GITHUB_TOKEN.
"""
import json
import os
import sys
import urllib.request

CLOSE_TITLES = (
    "M001 — Foundation & Local Generator",
    "M002 — Six Formats & Ground Truth",
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
    _, milestones = api("GET", "/milestones?state=all&per_page=100")
    by_title = {m["title"]: m for m in milestones}
    closed = skipped = 0
    for title in CLOSE_TITLES:
        ms = by_title.get(title)
        if ms is None:
            print(f"NOT FOUND: {title}")
            continue
        if ms["state"] == "closed":
            print(f"Skip (already closed): {title}")
            skipped += 1
            continue
        if ms["open_issues"] != 0:
            print(f"REFUSE: {title} still has {ms['open_issues']} open issues")
            continue
        api("PATCH", f"/milestones/{ms['number']}", {"state": "closed"})
        print(f"Closed milestone: {title} ({ms['closed_issues']} issues closed)")
        closed += 1
    print(f"Done. Closed: {closed}, already closed: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
