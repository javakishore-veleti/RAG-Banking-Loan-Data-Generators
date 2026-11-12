#!/usr/bin/env python3
"""
Bulk-create GitHub issues + milestones from GITHUB_ISSUES.md.

Why this script exists: the Muse GitHub connector asks for a fresh
approval for *every* issue write (127 issues = 127+ approvals).
This script runs *inside* GitHub Actions instead, using the repo's
own GITHUB_TOKEN, so one manual workflow run creates everything
with no per-issue approvals.

Usage (GitHub Actions — see.github/workflows/create-issues.yml):
    python3 scripts/create_issues.py

The same script creates the indexing plan too (see
.github/workflows/create-index-issues.yml), via env vars:
    PLAN_FILE=GITHUB_ISSUES_INDEXING.md \
    EXPECTED_MILESTONES=2 EXPECTED_EPICS=5 EXPECTED_FEATURES=13 \
    EXPECTED_STORIES=35 \
    PLAN_SCOPE="Data indexing only. No retrieval, reranking, agents, or UI." \
        python3 scripts/create_issues.py

Usage (local, with a PAT — one token, no per-issue approvals):
    GH_TOKEN=<token> GH_REPO=javakishore-veleti/RAG-Banking-Loan-Data-Generators \
        python3 scripts/create_issues.py

Behaviour:
  - Parses the plan file in the repo root (milestones, epics,
    features, stories) — Datagen plan: 5 milestones, 9 epics,
    33 features, 85 stories, all with 3-digit IDs (M001, E001,
    F001, S001). Indexing plan: 2 milestones (M006–M007),
    5 epics (E010–E014), 13 features (F034–F046), 35 stories
    (S086–S120).
  - Creates the 5 milestones, the labels `epic` / `feature` / `story`
    (if missing), then the issues in order: epics, features, stories.
  - Topical labels are added on top of the type label, per epic /
    feature / story: aws, s3, dynamodb, sqs, batch, lambda,
    step-functions, cloudformation, ecr, cloudwatch, cloudtrail,
    datagen-wf, index-wf, github-actions, infra-setup, infra-destroy,
    data-delete, generator, format-pdf/docx/xlsx/csv/txt/png,
    manifest, partitioning, uniqueness, dedup, realism, testing,
    docs, observability, and the indexing labels bedrock, pgvector,
    opensearch, embeddings, data-indexing, chunking, metadata, rds,
    hybrid-search. See TOPIC_LABELS below.
  - Idempotent: issues are skipped if an issue with the same title
    already exists (E001–E007 were created earlier by hand and are
    skipped, not duplicated). Safe to re-run. On a re-run, existing
    issues are PATCHed with their (new) labels + milestone, so a
    label change is applied to already-created issues too.
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

REPO = os.environ.get("GH_REPO", "javakishore-veleti/RAG-Banking-Loan-Data-Generators")
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
        if status!= 200 or not data:
            return out
        out.extend(data)
        if len(data) < 100:
            return out
        page += 1


# --- Parse the plan file -------------------------------------------------
# PLAN_FILE env selects the plan (default GITHUB_ISSUES.md; the
# indexing plan is GITHUB_ISSUES_INDEXING.md). Expected counts are
# env-vars too, so the same script validates either plan.
PLAN = Path(__file__).resolve().parents[1] / os.environ.get("PLAN_FILE", "GITHUB_ISSUES.md")
PLAN_NAME = PLAN.name
PLAN_SCOPE = os.environ.get(
    "PLAN_SCOPE",
    "Synthetic data generation only. No RAG ingestion, chunking, embedding, or retrieval.")
EXPECTED = (
    int(os.environ.get("EXPECTED_MILESTONES", "5")),
    int(os.environ.get("EXPECTED_EPICS", "9")),
    int(os.environ.get("EXPECTED_FEATURES", "33")),
    int(os.environ.get("EXPECTED_STORIES", "85")),
)
text = PLAN.read_text()

milestones = [] # (id, title, description)
for m in re.finditer(r"^\| (M\d{3}) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|", text, re.M):
    milestones.append((m.group(1), m.group(2).strip(), f"{m.group(3).strip()} — Exit: {m.group(4).strip()}"))

epics = {} # E001 -> {title, milestone}
# NOTE: E006's milestone is a range ("M003–M005") in the table and in its
# heading, so the milestone field must not require a single Mxxx — take
# the first milestone ID in the field. (A single-Mxxx regex dropped E006
# entirely and crashed the run with KeyError: 'E006'.)
for m in re.finditer(r"^\| (E\d{3}) \| ([^|]+) \| ([^|]+) \|", text, re.M):
    mid = re.search(r"M\d{3}", m.group(3))
    if mid:
        epics[m.group(1)] = {"title": m.group(2).strip(), "milestone": mid.group(0)}

# Epic milestone from the "### E001 — Title (M001)" headings overrides the table.
for m in re.finditer(r"^### (E\d{3}) — (.+?) \(([^)]+)\)", text, re.M):
    mid = re.search(r"M\d{3}", m.group(3))
    if mid:
        epics.setdefault(m.group(1), {})["title"] = m.group(2).strip()
        epics[m.group(1)]["milestone"] = mid.group(0)

features = [] # {id, title, epic, stories:[(id, text)]}
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

# Feature -> milestone, via its epic. Fail fast with a clear message
# instead of a bare KeyError if an epic is missing from the plan.
for f in features:
    if f["epic"] not in epics:
        sys.exit(f"ERROR: feature {f['id']} belongs to epic {f['epic']}, "
                 f"which was not parsed from GITHUB_ISSUES.md. Parsed epics: {sorted(epics)}")
    f["milestone"] = epics[f["epic"]]["milestone"]

if (len(milestones), len(epics), len(features),
        sum(len(f['stories']) for f in features))!= EXPECTED:
    sys.exit(f"ERROR: unexpected parse counts — milestones={len(milestones)}, "
             f"epics={len(epics)} ({sorted(epics)}), features={len(features)}, "
             f"stories={sum(len(f['stories']) for f in features)}. Expected {EXPECTED} "
             f"from {PLAN_NAME}.")

print(f"Parsed: {len(milestones)} milestones, {len(epics)} epics, "
      f"{len(features)} features, {sum(len(f['stories']) for f in features)} stories")

# --- Topical labels --------------------------------------------------------
# Type labels (epic/feature/story) are added separately. These are the
# additional labels, per epic and per feature. Stories inherit their
# feature's topical labels.
EPIC_LABELS = {
    "E001": ["generator"],
    "E002": ["generator", "format-pdf", "format-docx", "format-xlsx", "format-csv", "format-txt", "format-png"],
    "E003": ["manifest", "s3", "partitioning"],
    "E004": ["uniqueness"],
    "E005": ["realism"],
    "E006": ["dedup", "dynamodb", "s3"],
    "E007": ["aws", "cloudformation", "infra-setup", "s3", "dynamodb", "sqs", "cloudtrail"],
    "E008": ["aws", "datagen-wf", "github-actions", "batch", "lambda", "step-functions", "sqs"],
    "E009": ["observability", "cloudwatch", "testing", "docs", "infra-destroy", "data-delete"],
    "E010": ["data-indexing", "chunking", "metadata"],
    "E011": ["bedrock", "embeddings"],
    "E012": ["pgvector", "opensearch", "hybrid-search"],
    "E013": ["aws", "index-wf", "github-actions", "batch", "lambda", "step-functions", "sqs"],
    "E014": ["observability", "cloudwatch", "testing", "docs"],
}
FEATURE_LABELS = {
    "F001": ["generator"], "F002": ["generator"], "F003": ["generator"],
    "F004": ["format-pdf"], "F005": ["format-docx"], "F006": ["format-xlsx"],
    "F007": ["format-csv"], "F008": ["format-txt"], "F009": ["format-png"],
    "F010": ["manifest", "s3"], "F011": ["s3", "partitioning"],
    "F012": ["datagen-wf"],
    "F013": ["uniqueness"], "F014": ["uniqueness"], "F015": ["uniqueness"],
    "F016": ["realism"], "F017": ["realism"], "F018": ["realism"],
    "F019": ["dedup", "dynamodb"], "F020": ["dedup"], "F021": ["dedup"],
    "F022": ["aws", "cloudformation", "infra-setup", "s3"],
    "F023": ["aws", "cloudformation", "infra-setup", "batch", "ecr"],
    "F024": ["aws", "cloudformation", "infra-setup", "lambda", "step-functions"],
    "F031": ["aws", "cloudtrail", "observability"],
    "F025": ["github-actions", "datagen-wf"],
    "F026": ["aws", "sqs", "lambda"],
    "F027": ["aws", "batch", "sqs"],
    "F028": ["observability", "cloudwatch"],
    "F029": ["testing"], "F030": ["docs"],
    "F032": ["infra-destroy", "github-actions", "cloudformation"],
    "F033": ["data-delete", "s3", "dynamodb"],
    "F034": ["data-indexing"], "F035": ["chunking"], "F036": ["metadata", "data-indexing"],
    "F037": ["bedrock", "embeddings"], "F038": ["embeddings", "data-indexing"],
    "F039": ["pgvector", "rds"], "F040": ["opensearch", "hybrid-search"],
    "F041": ["lambda", "sqs"], "F042": ["batch", "sqs"],
    "F043": ["index-wf", "github-actions"], "F044": ["aws", "observability"],
    "F045": ["testing", "observability"], "F046": ["docs", "testing"],
}
LABEL_COLORS = {
    "epic": "5319e7", "feature": "0e8a16", "story": "fbca04",
    "aws": "ff9900", "s3": "569a31", "dynamodb": "4053d6", "sqs": "ff4f8b",
    "batch": "7f3fbf", "lambda": "ff9900", "step-functions": "7f3fbf",
    "cloudformation": "ff9900", "ecr": "569a31", "cloudwatch": "e36209",
    "cloudtrail": "e36209", "datagen-wf": "0e8a16", "github-actions": "2088ff",
    "infra-setup": "5319e7", "infra-destroy": "d73a4a", "data-delete": "d73a4a",
    "generator": "1d76db", "manifest": "bfdadc", "partitioning": "bfdadc",
    "uniqueness": "c2e0c6", "dedup": "c2e0c6", "realism": "c2e0c6",
    "testing": "0e8a16", "docs": "0075ca", "observability": "e36209",
    "format-pdf": "d73a4a", "format-docx": "1d76db", "format-xlsx": "0e8a16",
    "format-csv": "fbca04", "format-txt": "bfdadc", "format-png": "5319e7",
    "bedrock": "ff9900", "pgvector": "4053d6", "opensearch": "1d76db",
    "embeddings": "5319e7", "data-indexing": "0e8a16", "index-wf": "0e8a16",
    "rds": "4053d6", "chunking": "c2e0c6", "metadata": "bfdadc",
    "hybrid-search": "1d76db",
}

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
for name, color in LABEL_COLORS.items():
    status, _ = api("POST", "/labels", {"name": name, "color": color})
    print(f"Label {name}: {'created' if status in (200, 201) else 'exists'}")

# --- Issues -----------------------------------------------------------------
def create_issue(title, body, labels, milestone_id):
    """Create an issue, or PATCH an existing one with its labels/milestone.

    Re-running after a label change must update already-created issues,
    not skip them silently — otherwise new labels never land.
    """
    payload_labels = labels
    if title in existing:
        issue = existing[title]
        status, _ = api("PATCH", f"/issues/{issue['number']}",
                        {"labels": payload_labels,
                         **({"milestone": ms_numbers[milestone_id]}
                            if milestone_id in ms_numbers else {})})
        print(f"Updated (exists): {title} labels={payload_labels} ({status})")
        return issue
    payload = {"title": title, "body": body, "labels": payload_labels}
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
        print(f" (sub-issue link for #{child['number']} -> #{parent['number']} "
              f"not applied: {status}; body link remains)")

created_epics = {}
for eid, e in sorted(epics.items()):
    issue = create_issue(
        f"[Epic] {eid} — {e['title']}",
        f"## Epic — {eid} {e['title']}\n\n**Milestone:** {e['milestone']}\n"
        f"**Type:** Epic\n**Scope:** {PLAN_SCOPE}\n\n"
        f"See {PLAN_NAME} for the features and stories in this epic.",
        ["epic"] + EPIC_LABELS.get(eid, []), e["milestone"])
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
        ["feature"] + FEATURE_LABELS.get(f["id"], []), f["milestone"])
    if issue and epic_issue:
        add_sub_issue(epic_issue, issue)
    for sid, stext in f["stories"]:
        story = create_issue(
            f"[Story] {sid} — {stext}",
            f"## Story — {sid}\n\n**Parent feature:** "
            f"#{issue['number'] if issue else '?'} ({f['id']} — {f['title']})\n"
            f"**Milestone:** {f['milestone']}\n**Type:** Story\n\n{stext}",
            ["story"] + FEATURE_LABELS.get(f["id"], []), f["milestone"])
        if story and issue:
            add_sub_issue(issue, story)

print("Done.")
