---
name: rag-bank-loan-story-complete
description: Completes a rag-bank-loan GitHub story - checks every acceptance item in the story's spec with evidence, writes a ticked Acceptance list and a Done status line, then asks Kishore to approve the close before labelling, closing, flipping the sequencing mark, logging and syncing the feature. Use when the story is built, reviewed, merged to main and pushed, and Kishore runs /rag-bank-loan-story-complete N (or dry-run N).
disable-model-invocation: true
---

# rag-bank-loan-story-complete

Input: story issue number `N`, optionally `dry-run N`. Run `gh` from the repo root (it reads the repo from the git remote; never type owner/repo). Scratch files go in `runtime_data/tmp/` only, never `/tmp`.

**dry-run:** read-only commands run. Every write (issue edit, close, file edit, other skills) is printed as `WOULD RUN: <command>` and not sent. The body is still saved to `runtime_data/tmp/issue-N.md`, and the approval stop in step 7 is still shown, but nothing after it runs.

1. `gh issue view N --json title,body,labels,state`. Take the ID from the title `[Story] S047 — …`, the feature from `**Parent feature:** #F (F020 — …)` and the milestone from `**Milestone:** M003`. If the issue is already closed, say so; outside dry-run, stop.
2. Find the spec: `ls docs/superpowers/specs/*-S047-*-design.md`. If there is no spec, or it has no `## Acceptance` section, stop and say: "No acceptance criteria for S047: expected `docs/superpowers/specs/YYYY-MM-DD-S047-<topic>-design.md` with a `## Acceptance` section. Add it (written during brainstorming), then run this again." Do not invent items.
3. Prove each acceptance item with evidence: a test, a command and its result, or a file path. For a code story run both test commands from `.github/workflows/ci.yml`:
   `python -m pytest Middleware/Workflows/Datagen/tests/ -q` and `python -m pytest Middleware/Workflows/DataIndexing/tests/ -q` (`python3` if `python` is not on the PATH; install nothing without Kishore's OK). If any item is not proven or any test fails, stop and list what is missing. Do not tick it.
4. Work from the main checkout, not a story worktree. The story branch must already be merged into `main` and `main` pushed; if not, stop and say so. If `git status -s` shows changes or `git status -sb` shows `main` ahead, run `rag-bank-loan-commit-push N` first.
5. Commits: `git log --format=%h --grep="#N:"`. If none are found (older stories predate the `S047 #76:` form), say so plainly and use `commits: none tagged` below. Do not fail.
6. Build the new body in `runtime_data/tmp/issue-N.md`. Time: `date '+%F %H:%M'`. Right after the `**Type:**` line, replace any `**Status:**` line (or add one) with:
   `**Status:** Done — <one sentence on what was built> (completed YYYY-MM-DD HH:MM; commits `a1b2c3d`, `e4f5a6b`).`
   Under it add `**Acceptance:**` and one `- [x] <item> — <evidence>` line per spec item. Keep the rest of the body as is.
7. **STOP — closing needs Kishore's approval.** Show the close list (`#N S047 — <title>`) and the full new body, then ask: "Close #N (S047)? Reply yes to proceed." Do nothing more until he says yes. Anything other than a clear yes means do not close.
8. After yes, in order:
   - `gh issue edit N --remove-label "status: in-progress" --add-label "status: done" --body-file runtime_data/tmp/issue-N.md` (ignore "label not found" on a label the issue never had).
   - `gh issue close N --reason completed`.
   - In `GIT_ISSUES_SEQUENCING.md` change `S047 #N ⬜` to `S047 #N ✅` on that story's line only.
   - `rag-bank-loan-milestone-log N`. Skip it if `docs/Project_Management/Issues/Milestone_NNN.md` does not exist; never create it here.
   - `rag-bank-loan-commit-push N` with the summary `complete story` (it stages `GIT_ISSUES_SEQUENCING.md` and the milestone file by name).
   - `rag-bank-loan-progress-sync` on `F`.
9. If every story under `F` in `GIT_ISSUES_SEQUENCING.md` is now ✅, end with: "All stories of #F (F020) are done. Run `/rag-bank-loan-feature-complete F`." Otherwise name the next ⬜ story of `F` in ID order from that file.
10. Never close the feature or the epic here.
