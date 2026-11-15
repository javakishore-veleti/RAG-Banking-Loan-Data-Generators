# Milestone M003 - Uniqueness & Realism

**Scope:** descriptions are unique enough for RAG and seeded from real artifacts, and the
generator never writes duplicates. Exit criteria (`GIT_ISSUES_SEQUENCING.md`): wording-only
mean ≤ 0.15 and same-type pairs > 0.5 ≤ 5% on 200 records — **already met** (0.128 and 1.5%,
`Middleware/Workflows/Datagen/uniqueness_report.md`) — and the dedup audit clean. Only epic
E006 (Deduplication) is left: F020 shard markers / idempotency and F021 the post-run dedup
audit. Out of scope: running in AWS (M004) and 200k-record scale (M005).

**Status:** open. 0 epics done, 0 features done, 0 stories done (4 left to build).

**Done before this log (29 closed):** epics E004 #4, E005 #5; features F013–F019
(#48, #52, #56, #60, #64, #67, #71); stories S027–S046 (#49–#74). See
`GIT_ISSUES_SEQUENCING.md`.

How to read this file:
- `#76` is the GitHub issue number. `S047` / `F020` / `E006` is the ID at the start of the
  issue title (`[Story] S047 — …`). The IDs are the build order.
- Section 1 is build order. Section 2 groups by epic/feature. Section 3 is the Superpowers
  command table with a Status/Started/Completed log per step. Section 4 is project skills.
- `GIT_ISSUES_SEQUENCING.md` stays the milestone-wide order and ✅/⬜ snapshot. This file is
  the per-step log. GitHub is the source of truth for open/closed.

## Contents

- [1. Table of contents (build order)](#1-table-of-contents-build-order)
  - [E006 - Deduplication](#e006---deduplication)
- [2. The same issues grouped by epic and feature](#2-the-same-issues-grouped-by-epic-and-feature)
- [3. Superpowers workflow](#3-superpowers-workflow)
- [4. Project skills](#4-project-skills-rag-bank-loan---rag-banking-loan-corpus)
- [5. Notes](#5-notes)

## 1. Table of contents (build order)

Epic by epic, then feature by feature, then story by story, in ID order
(see "How sequencing works" in `GIT_ISSUES_SEQUENCING.md`).

**Parallel tracks:** Track A `#76` then `#77` (same worker file); Track B `#79` then `#80`
(same audit). The two tracks touch different files and can run at the same time.

### E006 - Deduplication

| # | Issue | Key | Type | Title | Why here |
|---|---|---|---|---|---|
| 1 | #6 | E006 | Epic | Deduplication | Last open epic of M003; F019 (#71) already done |
| 2 | #75 | F020 | Feature | Shard marker & idempotency | Worker replay and retry safety |
| 3 | #76 | S047 | Story | Each shard writes a `.done` marker; replay skips finished shards. | Marker code exists in `batch_worker.py`; needs tests |
| 4 | #77 | S048 | Story | Deterministic S3 keys + DynamoDB upserts with identical values on retry. | Same worker file as S047, so after it |
| 5 | #78 | F021 | Feature | Post-run dedup audit | Proves no duplicates after a run |
| 6 | #79 | S049 | Story | Athena/Glue audit: `GROUP BY <unique fields> HAVING COUNT(*) > 1` must return 0 rows. | Audit needs the F019 natural key (done) |
| 7 | #80 | S050 | Story | Audit the *description* overlap too (see F013) — not just IDs. | Extends the S049 audit |

## 2. The same issues grouped by epic and feature

```
Epic #6  E006  Deduplication
|
+-- Feature #71  F019  Natural-hash dedup                      (done)
|     +-- #72  S044 · #73  S045 · #74  S046                    (done)
|
+-- Feature #75  F020  Shard marker & idempotency
|     +-- #76  S047  Each shard writes a .done marker; replay skips finished shards
|     +-- #77  S048  Deterministic S3 keys + DynamoDB upserts identical on retry
|
+-- Feature #78  F021  Post-run dedup audit
      +-- #79  S049  Audit: GROUP BY <unique fields> HAVING COUNT(*) > 1 returns 0 rows
      +-- #80  S050  Audit the description overlap too (see F013)
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

### F020 #75 - Shard marker & idempotency

| Issue | Step | Command | Status | Started | Completed |
|---|---|---|---|---|---|
| #76 | 1 | `/rag-bank-loan-story-start 76` | Done | 2026-11-15 12:01 | 2026-11-15 12:01 |
| #76 | 2 | `/brainstorming Story #76: worker `.done` marker - unit tests with in-memory S3/DynamoDB fakes; a replayed finished shard writes nothing; a shard without a marker runs` | Done | 2026-11-15 12:01 | 2026-11-15 12:04 |
| #76 | 3 | `/using-git-worktrees Story #76: branch s047-shard-done-marker` | Done | 2026-11-15 12:04 | 2026-11-15 12:05 |
| #76 | 4 | `/writing-plans Story #76` | Done | 2026-11-15 12:05 | 2026-11-15 12:06 |
| #76 | 5 | `/test-driven-development Story #76` | Done | 2026-11-15 12:06 | 2026-11-15 12:07 |
| #76 | 6 | `/subagent-driven-development Story #76` | Done | 2026-11-15 12:07 | 2026-11-15 12:07 |
| #76 | 7 | `/rag-bank-loan-commit-push 76` after every task (repeat) | Done | 2026-11-15 12:07 | 2026-11-15 12:07 |
| #76 | 8 | `/verification-before-completion Story #76` | Done | 2026-11-15 12:07 | 2026-11-15 12:07 |
| #76 | 9 | `/requesting-code-review Story #76` | Done | 2026-11-15 12:07 | 2026-11-15 12:10 |
| #76 | 10 | `/rag-bank-loan-commit-push 76` | Done | 2026-11-15 12:10 | 2026-11-15 12:10 |
| #76 | 11 | `/finishing-a-development-branch Story #76` | Done | 2026-11-15 12:10 | 2026-11-15 12:11 |
| #76 | 12 | `/rag-bank-loan-story-complete 76` | In progress | 2026-11-15 12:11 | - |
| #77 | 1 | `/rag-bank-loan-story-start 77` | Done | 2026-11-15 12:11 | 2026-11-15 12:11 |
| #77 | 2 | `/brainstorming Story #77: retry of a half-finished shard gives the same S3 keys and identical DynamoDB rows; no duplicates` | Done | 2026-11-15 12:11 | 2026-11-15 12:12 |
| #77 | 3 | `/using-git-worktrees Story #77: branch s048-deterministic-retry` | Done | 2026-11-15 12:12 | 2026-11-15 12:12 |
| #77 | 4 | `/writing-plans Story #77` | Done | 2026-11-15 12:12 | 2026-11-15 12:13 |
| #77 | 5 | `/test-driven-development Story #77` | Done | 2026-11-15 12:13 | 2026-11-15 12:14 |
| #77 | 6 | `/subagent-driven-development Story #77` | Done | 2026-11-15 12:14 | 2026-11-15 12:14 |
| #77 | 7 | `/rag-bank-loan-commit-push 77` after every task (repeat) | Done | 2026-11-15 12:14 | 2026-11-15 12:14 |
| #77 | 8 | `/verification-before-completion Story #77` | Done | 2026-11-15 12:14 | 2026-11-15 12:15 |
| #77 | 9 | `/requesting-code-review Story #77` | Done | 2026-11-15 12:15 | 2026-11-15 12:16 |
| #77 | 10 | `/rag-bank-loan-commit-push 77` | Done | 2026-11-15 12:16 | 2026-11-15 12:17 |
| #77 | 11 | `/finishing-a-development-branch Story #77` | Done | 2026-11-15 12:17 | 2026-11-15 12:18 |
| #77 | 12 | `/rag-bank-loan-story-complete 77` | In progress | 2026-11-15 12:18 | - |
| Feature #75 | 1 | `/rag-bank-loan-feature-complete 75` | In progress | 2026-11-15 12:01 | - |

### F021 #78 - Post-run dedup audit

| Issue | Step | Command | Status | Started | Completed |
|---|---|---|---|---|---|
| #79 | 1 | `/rag-bank-loan-story-start 79` | Done | 2026-11-15 12:01 | 2026-11-15 12:01 |
| #79 | 2 | `/brainstorming Story #79: dedup audit script on a run's manifest - GROUP BY the natural key HAVING COUNT(*) > 1 returns 0 rows locally; same SQL kept ready for Athena` | Done | 2026-11-15 12:01 | 2026-11-15 12:04 |
| #79 | 3 | `/using-git-worktrees Story #79: branch s049-dedup-audit` | Done | 2026-11-15 12:04 | 2026-11-15 12:05 |
| #79 | 4 | `/writing-plans Story #79` | Done | 2026-11-15 12:05 | 2026-11-15 12:06 |
| #79 | 5 | `/test-driven-development Story #79` | Done | 2026-11-15 12:06 | 2026-11-15 12:06 |
| #79 | 6 | `/subagent-driven-development Story #79` | Done | 2026-11-15 12:06 | 2026-11-15 12:08 |
| #79 | 7 | `/rag-bank-loan-commit-push 79` after every task (repeat) | Done | 2026-11-15 12:08 | 2026-11-15 12:08 |
| #79 | 8 | `/verification-before-completion Story #79` | Done | 2026-11-15 12:08 | 2026-11-15 12:08 |
| #79 | 9 | `/requesting-code-review Story #79` | Done | 2026-11-15 12:08 | 2026-11-15 12:11 |
| #79 | 10 | `/rag-bank-loan-commit-push 79` | Done | 2026-11-15 12:11 | 2026-11-15 12:11 |
| #79 | 11 | `/finishing-a-development-branch Story #79` | Done | 2026-11-15 12:11 | 2026-11-15 12:13 |
| #79 | 12 | `/rag-bank-loan-story-complete 79` | In progress | 2026-11-15 12:13 | - |
| #80 | 1 | `/rag-bank-loan-story-start 80` | Done | 2026-11-15 12:13 | 2026-11-15 12:13 |
| #80 | 2 | `/brainstorming Story #80: audit also runs the description-overlap check (uniqueness_check.py) and fails above the M003 limits` | Done | 2026-11-15 12:13 | 2026-11-15 12:14 |
| #80 | 3 | `/using-git-worktrees Story #80: branch s050-description-overlap-audit` | Done | 2026-11-15 12:14 | 2026-11-15 12:14 |
| #80 | 4 | `/writing-plans Story #80` | Done | 2026-11-15 12:14 | 2026-11-15 12:15 |
| #80 | 5 | `/test-driven-development Story #80` | Done | 2026-11-15 12:15 | 2026-11-15 12:15 |
| #80 | 6 | `/subagent-driven-development Story #80` | Done | 2026-11-15 12:15 | 2026-11-15 12:17 |
| #80 | 7 | `/rag-bank-loan-commit-push 80` after every task (repeat) | Done | 2026-11-15 12:17 | 2026-11-15 12:17 |
| #80 | 8 | `/verification-before-completion Story #80` | Done | 2026-11-15 12:17 | 2026-11-15 12:17 |
| #80 | 9 | `/requesting-code-review Story #80` | Done | 2026-11-15 12:17 | 2026-11-15 12:21 |
| #80 | 10 | `/rag-bank-loan-commit-push 80` | Done | 2026-11-15 12:21 | 2026-11-15 12:21 |
| #80 | 11 | `/finishing-a-development-branch Story #80` | In progress | 2026-11-15 12:21 | - |
| #80 | 12 | `/rag-bank-loan-story-complete 80` | Planned | - | - |
| Feature #78 | 1 | `/rag-bank-loan-feature-complete 78` | In progress | 2026-11-15 12:01 | - |

### E006 #6 - Deduplication

| Issue | Step | Command | Status | Started | Completed |
|---|---|---|---|---|---|
| Epic #6 | 1 | `/rag-bank-loan-epic-complete 6` | In progress | 2026-11-15 12:01 | - |

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
- **Decision (2026-11-15): local proof.** F020 is proven by worker tests with in-memory
  S3/DynamoDB fakes; F021 by a local audit on a generated run, with the same SQL kept ready
  for Athena. The live AWS proof moves to the M004 / M005 exit criteria (HANDOVER.md §4).
  No new dependencies: fakes are hand-written, not moto.
- Feature #75's S048 text says "S003 keys"; it means S3 keys (typo in the issue, left as is).
- `scripts/close_milestones.py` lists only M001 and M002; add M003 before closing the GitHub
  milestone with `close-milestones.yml`.
