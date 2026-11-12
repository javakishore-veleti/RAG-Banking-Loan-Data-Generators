#!/usr/bin/env python3
"""
Bulk-create GitHub issues + milestones from GITHUB_ISSUES.md.

Why this script exists: the Muse GitHub connector asks for a fresh
approval for *every* issue write (127 issues = 127+ approvals).
This script runs *inside* GitHub Actions instead, using the repo's
own GITHUB_TOKEN, so one manual workflow run creates everything
with no per-issue approvals.

Usage (GitHub Actions — see .github/workflows/create-issues.yml):
    python3 scripts/create_issues.py

Usage (local, with a PAT — one token, no per-issue approvals):
    GH_TOKEN=<token> GH_REPO=javakishore-veleti/RAG-Banking-Data-Generators \
        python3 scripts/create_issues.py

Behaviour:
  - Parses GITHUB_ISSUES.md in the repo root (milestones, epics,
    features, stories) — 5 milestones, 9 epics, 33 features,
    85 stories, all with 3-digit IDs (M001, E001, F001, S001).
  - Creates the 5 milestones, the labels `epic` / `feature` / `story`
    (if missing), then the issues in order: epics, features, stories.
  - Idempotent: issues are skipped if an issue with the same title
    already exists (E001–E007 were created earlier by hand and are
    skipped, not duplicated). Safe to re-run.
  - Links children as GitHub sub-issues of their parent when the
    API supports it; the body also names the parent, so the link
    survives even if the sub-issue call fails.
  - Assigns each issue to its milestone by number.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO = os.environ.get("GH_REPO", "javakishore-veleti/RAG-Banking-Data-Generators")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
if not TOKEN:
    sys.exit("Set GITHUB_TOKEN (Actions) or GH_TOKEN (local PAT) before running.")

OWNER, REPO_NAME = REPO.split("/", 1)
API = f"https://api.github.com/repos/{OWNER}/{REPO_NAME}"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "rag-corpus-create-issues",
}


def api(method, path, payload=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return e.code, {"error": body}


def paged(path):
    out, page = [], 1
    while True:
        status, data = api("GET", f"{path}?state=all&per_page=100&page={page}")
        if status != 200 or not data:
            return out
        out.extend(data)
        if len(data) < 100:
            return out
        page += 1


# --- Parse GITHUB_ISSUES.md -------------------------------------------------
PLAN = Path(__file__).resolve().parents[1] / "GITHUB_ISSUES.md"
text = PLAN.read_text()

milestones = []  # (id, title, description)
for m in re.finditer(r"^\| (M\d{3}) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|", text, re.M):
    milestones.append((m.group(1), m.group(2).strip(), f"{m.group(3).strip()} — Exit: {m.group(4).strip()}"))

epics = {}  # E001 -> {title, milestone}
for m in re.finditer(r"^\| (E\d{3}) \| ([^|]+) \| (M\d{3}) \|", text, re.M):
    epics[m.group(1)] = {"title": m.group(2).strip(), "milestone": m.group(3)}

# Epic milestone from the "### E001 — Title (M001)" headings overrides the table.
for m in re.finditer(r"^### (E\d{3}) — (.+?) \((M\d{3})\)", text, re.M):
    epics.setdefault(m.group(1), {})["title"] = m.group(2).strip()
    epics[m.group(1)]["milestone"] = m.group(3)

features = []  # {id, title, epic, stories:[(id, text)]}
current_epic = None
for line in text.splitlines():
    hm = re.match(r"^### (E\d{3}) —", line)
    if hm:
        current_epic = hm.group(1)
    fm = re.match(r"^\*\*(F\d{3}) — (.+?)\*\*$", line.strip())
    if fm:
        features.append({"id": fm.group(1), "title": fm.group(2).strip(),
                         "epic": current_epic, "stories": []})
    sm = re.match(r"^- (S\d{3})\. (.+)$", line.strip())
    if sm and features:
        features[-1]["stories"].append((sm.group(1), sm.group(2).strip()))

# Feature -> milestone, via its epic.
for f in features:
    f["milestone"] = epics[f["epic"]]["milestone"]

print(f"Parsed: {len(milestones)} milestones, {len(epics)} epics, "
      f"{len(features)} features, {sum(len(f['stories']) for f in features)} stories")

# --- Existing state (idempotency) -------------------------------------------
existing = {i["title"]: i for i in paged("/issues")}
print(f"Existing issues in repo: {len(existing)}")

# --- Milestones -------------------------------------------------------------
ms_numbers = {}
status, ms_list = api("GET", "/milestones?state=all&per_page=100")
for ms in ms_list if isinstance(ms_list, list) else []:
    ms_numbers[ms["title"].split(" — ")[0]] = ms["number"]
for mid, title, desc in milestones:
    if mid in ms_numbers:
        print(f"Milestone exists: {mid}")
        continue
    status, ms = api("POST", "/milestones",
                     {"title": f"{mid} — {title}", "description": desc, "state": "open"})
    if status in (200, 201):
        ms_numbers[mid] = ms["number"]
        print(f"Created milestone {mid}: {title}")
    else:
        print(f"FAILED milestone {mid}: {status} {ms}")

# --- Labels -----------------------------------------------------------------
for name, color in [("epic", "5319e7"), ("feature", "0e8a16"), ("story", "fbca04")]:
    status, _ = api("POST", "/labels", {"name": name, "color": color})
    print(f"Label {name}: {'created' if status in (200, 201) else 'exists'}")

# --- Issues -----------------------------------------------------------------
def create_issue(title, body, label, milestone_id):
    if title in existing:
        print(f"Skip (exists): {title}")
        return existing[title]
    payload = {"title": title, "body": body, "labels": [label]}
    if milestone_id in ms_numbers:
        payload["milestone"] = ms_numbers[milestone_id]
    status, issue = api("POST", "/issues", payload)
    if status not in (200, 201):
        print(f"FAILED {title}: {status} {issue}")
        return None
    existing[title] = issue
    print(f"Created #{issue['number']}: {title}")
    return issue


def add_sub_issue(parent, child):
    if not parent or not child:
        return
    status, _ = api("POST", f"/issues/{parent['number']}/sub_issues",
                    {"sub_issue_id": child["id"]})
    if status not in (200, 201):
        print(f"  (sub-issue link for #{child['number']} -> #{parent['number']} "
              f"not applied: {status}; body link remains)")

created_epics = {}
for eid, e in sorted(epics.items()):
    issue = create_issue(
        f"[Epic] {eid} — {e['title']}",
        f"## Epic — {eid} {e['title']}\n\n**Milestone:** {e['milestone']}\n"
        f"**Type:** Epic\n**Scope:** Synthetic data generation only. "
        f"No RAG ingestion, chunking, embedding, or retrieval.\n\n"
        f"See GITHUB_ISSUES.md for the features and stories in this epic.",
        "epic", e["milestone"])
    if issue:
        created_epics[eid] = issue

for f in features:
    epic_issue = created_epics.get(f["epic"])
    parent_ref = f"#{epic_issue['number']}" if epic_issue else f["epic"]
    issue = create_issue(
        f"[Feature] {f['id']} — {f['title']}",
        f"## Feature — {f['id']} {f['title']}\n\n**Parent epic:** {parent_ref} ({f['epic']})\n"
        f"**Milestone:** {f['milestone']}\n**Type:** Feature\n\n"
        + "\n".join(f"- **{sid}** {stext}" for sid, stext in f["stories"]),
        "feature", f["milestone"])
    if issue and epic_issue:
        add_sub_issue(epic_issue, issue)
    for sid, stext in f["stories"]:
        story = create_issue(
            f"[Story] {sid} — {stext}",
            f"## Story — {sid}\n\n**Parent feature:** "
            f"#{issue['number'] if issue else '?'} ({f['id']} — {f['title']})\n"
            f"**Milestone:** {f['milestone']}\n**Type:** Story\n\n{stext}",
            "story", f["milestone"])
        if story and issue:
            add_sub_issue(issue, story)

print("Done.")
