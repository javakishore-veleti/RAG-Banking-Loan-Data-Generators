# Milestone <MNNN> - <Milestone title>

<!--
Template. Copy to Milestone_NNN.md (M008 → Milestone_008.md) by hand when the milestone's
first story starts. Replace every <...> placeholder and the M008 example rows with the
milestone's own issues, taken from GIT_ISSUES_SEQUENCING.md. Delete this comment.
-->

**Scope:** <One or two sentences: what this milestone proves, and its exit criteria from
`GIT_ISSUES_SEQUENCING.md`. Say what is out of scope and which milestone owns it.>

**Status:** open. 0 epics done, 0 features done, 0 stories done (<S> left to build).

How to read this file:
- `#188` is the GitHub issue number. `S121` / `F047` / `E015` is the ID at the start of the
  issue title (`[Story] S121 — …`). The IDs are the build order.
- Section 1 is build order. Section 2 groups by epic/feature. Section 3 is the Superpowers
  command table with a Status/Started/Completed log per step. Section 4 is project skills.
- `GIT_ISSUES_SEQUENCING.md` stays the milestone-wide order and ✅/⬜ snapshot. This file is
  the per-step log. GitHub is the source of truth for open/closed.

## Contents

- [1. Table of contents (build order)](#1-table-of-contents-build-order)
  - [<ENNN> - <Epic title>](#ennn---epic-title)
- [2. The same issues grouped by epic and feature](#2-the-same-issues-grouped-by-epic-and-feature)
- [3. Superpowers workflow](#3-superpowers-workflow)
- [4. Project skills](#4-project-skills-rag-bank-loan---rag-banking-loan-corpus)
- [5. Notes](#5-notes)

## 1. Table of contents (build order)

Epic by epic, then feature by feature, then story by story, in ID order
(see "How sequencing works" in `GIT_ISSUES_SEQUENCING.md`).

### <ENNN> - <Epic title>

| # | Issue | Key | Type | Title | Why here |
|---|---|---|---|---|---|
| 1 | #<E> | <ENNN> | Epic | <Epic title> | Parent of all <MNNN> work |
| 2 | #<F> | <FNNN> | Feature | <Feature title> | Parent of its stories |
| 3 | #<N> | <SNNN> | Story | <Story title> | <Why it comes here> |

Example (M008):

| # | Issue | Key | Type | Title | Why here |
|---|---|---|---|---|---|
| 1 | #182 | E015 | Epic | Local container platform | Parent of the container work |
| 2 | #187 | F047 | Feature | Postgres via docker-compose | First container; M009 needs it |
| 3 | #188 | S121 | Story | Postgres docker-compose.yaml: port, volume, healthcheck | Server before schemas (S122) |

## 2. The same issues grouped by epic and feature

```
Epic #<E>  <ENNN>  <Epic title>
|
+-- Feature #<F>  <FNNN>  <Feature title>
      +-- #<N>  <SNNN>  <Story title>
```

Example (M008):

```
Epic #182  E015  Local container platform
|
+-- Feature #187  F047  Postgres via docker-compose
      +-- #188  S121  Postgres docker-compose.yaml: port, volume, healthcheck
```

## 3. Superpowers workflow

One chat per story (or one parallel agent per independent story). Run the commands of a story
from top to bottom. `/rag-bank-loan-*` are the project skills (section 4); the others come from
the Superpowers plugin. In Claude Code these are `/superpowers:<name>`.

Every command has its own row with a **Status** (`Planned`, `In progress` or `Done`), a
**Started** time and a **Completed** time (`date '+%F %H:%M'`, `-` until set). The step that is
`In progress` is the one to run next. You do not edit the table: when a step finishes,
`/rag-bank-loan-milestone-log N` marks it `Done` and starts the next step.
`/rag-bank-loan-story-start` and `/rag-bank-loan-story-complete` log their own step. The change
is saved in the next `/rag-bank-loan-commit-push`.

Standard code story, with `N` as the issue number:

| Step | Command | What it does |
|---|---|---|
| 1 | `/rag-bank-loan-story-start N` | Marks the story in progress and refreshes the feature and epic |
| 2 | `/brainstorming Story #N ...` | Confirms the design against the issue; writes the spec with acceptance criteria in `docs/superpowers/specs/` |
| 3 | `/using-git-worktrees Story #N: branch ...` | Creates an isolated workspace on a new branch for the story |
| 4 | `/writing-plans Story #N` | Breaks the story into small tasks with exact files and verification steps (`docs/superpowers/plans/`) |
| 5 | `/test-driven-development Story #N` | Loads RED-GREEN-REFACTOR for step 6 |
| 6 | `/subagent-driven-development Story #N` | Builds each task with a fresh subagent (or `/executing-plans`) |
| 7 | `/rag-bank-loan-commit-push N` | After every task of step 6 (repeat) |
| 8 | `/verification-before-completion Story #N` | Tests, acceptance |
| 9 | `/requesting-code-review Story #N` | Review against the plan |
| 10 | `/rag-bank-loan-commit-push N` | Review fixes |
| 11 | `/finishing-a-development-branch Story #N` | PR → main when CI green (preferred); merge only green |
| 12 | `/rag-bank-loan-story-complete N` | Ticks acceptance, closes the story after Kishore's yes, refreshes the feature |

If a test fails and you do not know why, run `/systematic-debugging Story #N` before changing
code.

After the last story of a feature: one row `Feature #F | 1 | /rag-bank-loan-feature-complete F`.
After the last feature of an epic: one row `Epic #E | 1 | /rag-bank-loan-epic-complete E`.

### <ENNN> - <Epic title>

| Issue | Step | Command | Status | Started | Completed |
|---|---|---|---|---|---|
| #<N> | 1 | `/rag-bank-loan-story-start <N>` | Planned | - | - |
| #<N> | 2 | `/brainstorming Story #<N>: <what to decide>` | Planned | - | - |
| ... | ... | ... | ... | ... | ... |
| #<N> | 12 | `/rag-bank-loan-story-complete <N>` | Planned | - | - |
| Feature #<F> | 1 | `/rag-bank-loan-feature-complete <F>` | Planned | - | - |
| Epic #<E> | 1 | `/rag-bank-loan-epic-complete <E>` | Planned | - | - |

Example (M008, E015 - Local container platform):

| Issue | Step | Command | Status | Started | Completed |
|---|---|---|---|---|---|
| #188 | 1 | `/rag-bank-loan-story-start 188` | Planned | - | - |
| #188 | 2 | `/brainstorming Story #188: Postgres docker-compose.yaml under CICD/Local/Postgres - port, named volume, healthcheck; postgres/postgres credentials` | Planned | - | - |
| #188 | 3 | `/using-git-worktrees Story #188: branch s121-postgres-docker-compose` | Planned | - | - |
| #188 | 4 | `/writing-plans Story #188` | Planned | - | - |
| #188 | 5 | `/test-driven-development Story #188` | Planned | - | - |
| #188 | 6 | `/subagent-driven-development Story #188` | Planned | - | - |
| #188 | 7 | `/rag-bank-loan-commit-push 188` after every task (repeat) | Planned | - | - |
| #188 | 8 | `/verification-before-completion Story #188` | Planned | - | - |
| #188 | 9 | `/requesting-code-review Story #188` | Planned | - | - |
| #188 | 10 | `/rag-bank-loan-commit-push 188` | Planned | - | - |
| #188 | 11 | `/finishing-a-development-branch Story #188` | Planned | - | - |
| #188 | 12 | `/rag-bank-loan-story-complete 188` | Planned | - | - |
| Feature #187 | 1 | `/rag-bank-loan-feature-complete 187` | Planned | - | - |
| Epic #182 | 1 | `/rag-bank-loan-epic-complete 182` | Planned | - | - |

## 4. Project skills (`rag-bank-loan` = RAG Banking Loan corpus)

The skills live in the repo's project skills folder, one folder per skill
(`rag-bank-loan-*/SKILL.md`). Each takes a GitHub issue number.

| Command | When | What it does |
|---|---|---|
| `/rag-bank-loan-story-start N` | Before the first Superpowers command of a story | Adds label `status: in-progress` and a `**Status:**` line, moves the parent feature and epic to in progress |
| `/rag-bank-loan-story-complete N` | After review and the final commit | Checks the spec's acceptance criteria, closes the story after Kishore's yes, flips ⬜ → ✅ in `GIT_ISSUES_SEQUENCING.md`, refreshes the feature |
| `/rag-bank-loan-feature-complete N` | When every story of the feature is done | Marks the feature done and closes it after Kishore's yes, refreshes the epic |
| `/rag-bank-loan-epic-complete N` | When every feature of the epic is done | Marks the epic done and closes it after Kishore's yes, and marks this file complete when it is the last epic |
| `/rag-bank-loan-milestone-log N` | After each workflow step finishes | Marks the `In progress` step for issue N as `Done`, starts the next step |
| `/rag-bank-loan-commit-push N` | After every task, and at the end of each story | Runs the pytest commands, commits `S121 #188: <summary>` as Kishore (no AI trailer), pushes |
| `/rag-bank-loan-progress-sync N` | Used by the skills above | Rebuilds the `**Progress:** D of T done` line of a feature or epic from its children |

Every skill that writes takes `dry-run`: nothing is changed, the would-be result goes to
`runtime_data/tmp/`.

## 5. Notes

- **Order and ✅/⬜:** `GIT_ISSUES_SEQUENCING.md`. Update it when an issue closes; this file
  does not replace it.
- **Specs / plans** under `docs/superpowers/specs/` and `docs/superpowers/plans/` appear when a
  story runs `/brainstorming` and `/writing-plans`. They do not exist until a story starts.
- **Gates:** do not start the next milestone before this one's exit criteria pass (see "The
  gates between milestones" in `GIT_ISSUES_SEQUENCING.md`).
- **Closing** an issue needs Kishore's approval. `HANDOVER.md` is updated when the milestone's
  status changes.
- **PR → main**, merge only when CI is green. Git author is `git config user.*`; no
  `Co-Authored-By` or other AI trailer.
- **Scratch files** go in `runtime_data/tmp/` (git-ignored), never `/tmp`.
- <Milestone-specific notes, decisions and follow-ups.>
