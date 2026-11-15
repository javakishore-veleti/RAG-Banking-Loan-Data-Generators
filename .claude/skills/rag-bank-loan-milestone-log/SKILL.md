---
name: rag-bank-loan-milestone-log
description: Logs workflow progress of a rag-bank-loan (RAG Banking Loan corpus) story, feature or epic in its milestone file docs/Project_Management/Issues/Milestone_NNN.md - marks the step in progress as Done with the current date and time and starts the next step. Use when a rag-bank-loan- skill says to run rag-bank-loan-milestone-log, after each Superpowers workflow step of a milestone story finishes, or when the user runs /rag-bank-loan-milestone-log N.
---

# rag-bank-loan-milestone-log

Input: GitHub issue number `N` (story, feature or epic), optionally `begin`, optionally `dry-run`.

File: `docs/Project_Management/Issues/Milestone_NNN.md`, section 3. Find the milestone with
`gh issue view N --json milestone -q .milestone.title` (for example `M008 — Local Development
Platform` → `Milestone_008.md`). Every command has a row:
`Issue | Step | Command | Status | Started | Completed`. Status is `Planned`, `In progress` or
`Done`; times are `YYYY-MM-DD HH:MM` or `-`.

1. If the milestone file does not exist, stop and say so. Do not create it: a milestone file is
   made by hand from `Milestone_TEMPLATE.md` when the milestone's first story starts.
2. Find the rows of `N`: first cell is `#N`, `#N (...)`, `Feature #N` or `Epic #N`. They are in
   step order. If there are none, stop and say so (the issue is not in the table: add it first).
3. Now: `date '+%F %H:%M'` (date and local time, for example `2026-11-15 16:30`). Write it in
   the Started and Completed cells.
4. `begin`: set the first row to `In progress` with Started now. Do nothing else.
5. No `begin`: take the row of `N` that is `In progress`.
   - If none is, but the first row is `Planned` (a feature or epic never begun), set it to
     `In progress` with Started now first.
   - If none is and every row is `Done`, stop and say so.
   - Set that row to `Done` with Completed now. If its Started is `-`, set it to now as well.
   - Set the next row of `N`, if any, to `In progress` with Started now.
6. Change only the Status, Started and Completed cells. Leave Issue, Step and Command exactly
   as they are.
7. Refresh the `**Status:**` counts at the top. A story is an issue whose last row is a
   `/rag-bank-loan-story-complete`. "left to build" is the number of those whose last row is not
   `Done`; "done" is the number whose last row is `Done`. Count features (last row
   `/rag-bank-loan-feature-complete`) and epics (`/rag-bank-loan-epic-complete`) the same way.
   Leave `GIT_ISSUES_SEQUENCING.md` alone: its ✅/⬜ flips when an issue closes.
8. `dry-run`: make no edit to the real milestone file. Write the would-be file to
   `runtime_data/tmp/Milestone_NNN.md` (never `/tmp`), print one `WOULD RUN:` line per changed
   row (`WOULD RUN: #188 step 2 Planned → In progress, Started 2026-11-15 16:30`), and stop.
9. Do not commit. The change goes out with the next `rag-bank-loan-commit-push`, which includes
   this file when it is modified.

Steps that repeat: the pair `subagent-driven-development` (step 6) and
"`/rag-bank-loan-commit-push N` after every task" (step 7) is logged once each, after the
commit of the final task.
