# Design — `rag-bank-loan` project skills (harness-agnostic)

Date: 2026-11-15 · Owner: Kishore · Status: **Approved 2026-11-15** (Q1–Q3 answered)

## 1. Goal

Give this repo the same Superpowers-extended workflow that Consumer-Complaints-Agentic-App
(project code `ccaa`) uses, under the project code **`rag-bank-loan`**. The skills must work in
any agent tool that reads the Agent Skills format (`SKILL.md` with `name` + `description`
front matter): Claude Code, Cursor, GitHub Copilot, Codex.

The 12-step story flow is the fixed contract (unchanged from CCAA):

| Step | Command | Source |
|---|---|---|
| 1 | `rag-bank-loan-story-start N` | project skill |
| 2 | `brainstorming Story #N …` | Superpowers |
| 3 | `using-git-worktrees Story #N: branch …` | Superpowers |
| 4 | `writing-plans Story #N` | Superpowers |
| 5 | `test-driven-development Story #N` | Superpowers |
| 6 | `subagent-driven-development Story #N` (or `executing-plans`) | Superpowers |
| 7 | `rag-bank-loan-commit-push N` after every task | project skill |
| 8 | `verification-before-completion Story #N` | Superpowers |
| 9 | `requesting-code-review Story #N` | Superpowers |
| 10 | `rag-bank-loan-commit-push N` (review fixes) | project skill |
| 11 | `finishing-a-development-branch Story #N` | Superpowers |
| 12 | `rag-bank-loan-story-complete N` | project skill |

`systematic-debugging` before changing code on an unexplained test failure.

## 2. What exists today (facts checked 2026-11-15)

- CCAA has 7 skills in `.cursor/skills/`: story-start, commit-push, milestone-log,
  progress-sync, story-complete, feature-complete, epic-complete. Only Cursor finds them.
- Superpowers 7.0.2 is installed in this repo at project scope (`.claude/settings.json`) and has
  every Superpowers skill the table names.
- This repo's issues differ from CCAA's:
  - Title: `[Story] S047 — …`, `[Feature] F020 — …`, `[Epic] E006 — …` (CCAA: `M03-0006 …`).
  - Body: `**Parent feature:** #75 (F020 …)` on stories, `**Parent epic:** #6 (E006)` on
    features, `**Milestone:** M003`. No `**Status:**` line, no `**Progress:**` line, no
    acceptance checklist. Feature bodies list children by ID (`- **S047** …`), not `#number`.
  - Labels: type + topic (`story`, `dedup`). No `status:` labels.
- Execution order and ✅/⬜ status live in `GIT_ISSUES_SEQUENCING.md`. There is no per-step
  log (CCAA's `Milestone_MM.md` §3).
- Tests: the `pytest` commands in `.github/workflows/ci.yml` (Datagen + DataIndexing). No lint.
- `gh` CLI is **not installed** on this machine; the skills depend on it.
- Repo rule: never close an issue without Kishore approving the close list.

## 3. Approaches considered

1. **One canonical folder + symlinks (chosen).** Skills live once in `.agents/skills/`;
   `.claude/skills`, `.cursor/skills`, `.github/skills` are symlinks to it. No copies, no drift.
   Cost: Windows checkouts need `core.symlinks=true`.
2. Canonical folder + sync script and CI drift check. Works everywhere, but four copies.
3. Claude Code plugin. Cleanest in Claude Code, but ties the skills to one tool.

## 4. Design

### 4.1 Layout

```
.agents/
  skills/
    rag-bank-loan-story-start/SKILL.md
    rag-bank-loan-commit-push/SKILL.md
    rag-bank-loan-milestone-log/SKILL.md
    rag-bank-loan-progress-sync/SKILL.md
    rag-bank-loan-story-complete/SKILL.md
    rag-bank-loan-feature-complete/SKILL.md
    rag-bank-loan-epic-complete/SKILL.md
.claude/skills  -> ../.agents/skills
.cursor/skills  -> ../.agents/skills
.github/skills  -> ../.agents/skills
docs/Project_Management/Issues/Milestone_NNN.md   # per-step log, one per milestone (§4.4)
runtime_data/tmp/                                  # scratch, git-ignored
```

The discovery path of each tool is verified as the first plan task. If a tool does not read its
path, it is dropped from the list and noted, not worked around.

### 4.2 Repo-specific, not a generic port

The skills take CCAA's *ideas* and are written for this repo directly. There is no shared config
layer and no attempt to keep them portable back to CCAA. Values are written into the skills:

- Keys: `S047` / `F020` / `E006` from titles `[Story] S047 — …`.
- Commit: `S047 #76: <summary>`; work not tied to a story: `M008: <summary>`.
- Tests: the two `pytest` commands from `ci.yml` (Datagen, DataIndexing), plus a service's
  own tests once M008+ code exists. No lint step today.
- Order and ✅/⬜: `GIT_ISSUES_SEQUENCING.md`. Per-step log: `Milestone_NNN.md` (§4.4).
- Specs / plans: `docs/superpowers/specs/`, `docs/superpowers/plans/`. Scratch:
  `runtime_data/tmp/` (git-ignored).
- Repo rules built in: close only with Kishore's approval; HANDOVER.md updated when a
  milestone's status changes; data deleted before infra (AWS-009 before AWS-010).

### 4.3 Skill changes vs CCAA

- **Tool-neutral wording.** No tool names. CCAA's "Cursor's git wrapper adds a trailer" becomes
  "whichever tool you are, check the last commit for any AI co-author trailer and rebuild it
  without one" (Q1: mandatory).
- **Superpowers names** are written plain (`brainstorming`); one line notes Claude Code's
  namespaced form `/superpowers:brainstorming`.
- **Parent lookup** follows this repo's bodies: story → `**Parent feature:** #F`; feature →
  `**Parent epic:** #E`.
- **Status markers.** `story-start` appends a `**Status:** In progress — started …` line
  (bodies have none today) and adds label `status: in-progress`. Labels `status: in-progress`
  and `status: done` must be created once (Q2).
- **Acceptance.** Bodies have no checklist. `story-complete` verifies the acceptance criteria in
  the story's spec (`docs/superpowers/specs/`), written during step 2, and copies them into the issue body as
  a ticked `- [x]` list with evidence.
- **Closing needs approval.** `story-complete`, `feature-complete` and `epic-complete` stop
  before `gh issue close`, show the close list, and close only after Kishore says yes. They
  also flip ⬜ → ✅ for the closed IDs in `GIT_ISSUES_SEQUENCING.md`.
- **progress-sync** rebuilds a `**Progress:** D of T done` line under the existing child list,
  matching children by ID (`S047`) to issue numbers via title search.
- **commit-push**: stage by name only; run the pytest commands; one-line `S047 #76: …`
  message; author = `git config user.*`; push; confirm not ahead.
- `disable-model-invocation: true` stays on start / complete skills (tools that ignore it just
  treat them as normal skills).

### 4.4 Per-step log for this repo

`Milestone_NNN.md` follows CCAA's sections (build order, grouping, step table with
Status/Started/Completed, skills, notes). It is created **when a milestone's first story
starts**, not for all ten milestones up front. `GIT_ISSUES_SEQUENCING.md` stays the
milestone-wide order and ✅/⬜ snapshot.

### 4.5 Prerequisite

`gh` 2.104.0 is installed (2026-11-15, `~/.local/bin/gh`, official release, checksum
verified; Homebrew on this laptop is broken). Kishore runs `! gh auth login` once. Without
auth no skill that touches issues can run.

## 5. Out of scope

- Changing the CCAA repo or its skills.
- Back-filling Status/Progress lines into all 248 existing issues (done lazily as stories start).
- Creating milestone log files for milestones not yet started.

## 6. Decisions (answered by Kishore 2026-11-15)

- **Q1 — No co-author, ever.** Every commit is authored by Kishore (`git config user.*`) and
  carries no `Co-Authored-By` or other AI trailer, whichever tool made it. `commit-push` checks
  the last commit and rebuilds it without a trailer before pushing. Mandatory.
- **Q2 — Yes.** Create labels `status: in-progress` and `status: done` in this repo.
- **Q3 — Later.** Milestone work (and its first `Milestone_NNN.md`) starts after this skills
  plumbing is done.

## 7. Verification

- Each tool lists the seven `rag-bank-loan-*` skills from its own path (checked per tool).
- Dry run of `rag-bank-loan-story-start` and `-commit-push` on one real story, with the issue
  edits shown before they are sent.
- No skill mentions a tool by name (grep for `Cursor`, `Claude`, `Copilot`, `Codex`), except
  the one line about Claude Code's `/superpowers:` prefix.
