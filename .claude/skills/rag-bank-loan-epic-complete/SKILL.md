---
name: rag-bank-loan-epic-complete
description: Completes a rag-bank-loan epic issue (`[Epic] E006 — …`) once all its features are closed - writes the Done status line, and after Kishore approves, labels it done, closes it, ticks it in GIT_ISSUES_SEQUENCING.md, logs and commits; if the milestone has nothing open left, proposes the milestone status updates. Use when the user runs /rag-bank-loan-epic-complete N (optionally with dry-run).
disable-model-invocation: true
---

# rag-bank-loan-epic-complete

Input: epic issue number `N`, optional `dry-run`. Run `gh` from the repo root (it reads the repo from the git remote; never type owner/repo). Scratch files only in `runtime_data/tmp/`, never `/tmp`.

**dry-run:** read-only calls run as normal; every write is printed as `WOULD RUN: <command>` instead; the new body is still saved to `runtime_data/tmp/issue-N.md`; each approval stop is still shown and nothing after it runs.

1. Run `rag-bank-loan-progress-sync` on `N`. It maps each feature ID the body lists (`- **F019** …` bullets or a `Features: F019 …, F020 …` line) to its issue number and state and writes the `**Progress:**` line (in dry-run it only prints it).
2. If any feature is not closed, stop and list them: `F020 #75, F021 #78 still open.` Change nothing and write no body file.
3. Read the epic ID (`E006`) from the title and the milestone code from `**Milestone:** M003 …`. If the epic is already closed, say so; the close command is then a no-op but the label, body and ✅ are still checked.
4. Build the new body in `runtime_data/tmp/issue-N.md`: put `**Status:** Done — All T features are done: F019 #71, F020 #75, F021 #78.` on its own line right after `**Type:**` (replace an existing `**Status:**` line). T is the feature count; list features in ID order.
5. **STOP for approval.** Show the close list (`#6 E006 — Deduplication`), the new body, and the commands below. Wait for Kishore's explicit yes. Anything else: change nothing.
6. After yes, run in order:
   - `gh issue edit N --remove-label "status: in-progress" --add-label "status: done" --body-file runtime_data/tmp/issue-N.md` (ignore a "label not found" on remove).
   - `gh issue close N --reason completed`
   - In `GIT_ISSUES_SEQUENCING.md`, flip ⬜ → ✅ on that epic's heading only: `### E006 #6 ⬜ …` → `### E006 #6 ✅ …`.
   - `rag-bank-loan-milestone-log N`, only if `docs/Project_Management/Issues/Milestone_NNN.md` exists (NNN from M003). Never create it; if missing, say "no milestone log yet, skipped".
   - `rag-bank-loan-commit-push` with the message `M003: complete epic E006 #6`.
7. Milestone check. Get the exact title: `gh issue view N --json milestone --jq .milestone.title` (or match the code in `gh api 'repos/{owner}/{repo}/milestones?state=all'`; gh fills the placeholders). Run `gh issue list --milestone "<title>" --state open --json number,title`.
   - Open issues left: say "M003 still has K open issues (…); milestone status unchanged." and stop.
   - None left: **STOP for approval** again and show the proposed edits: the M003 row's Status in the `HANDOVER.md` §2 table (e.g. `CLOSED (36/36)`), the `Status:` line of the M003 section in `GIT_ISSUES_SEQUENCING.md` (e.g. `**Closed — 36 of 36**`), and `**Status: complete.**` in `Milestone_NNN.md` if that file exists. After yes, make them and run `rag-bank-loan-commit-push` with `M003: mark milestone complete`.
8. Remind Kishore: the milestone's exit criteria (`HANDOVER.md` §2 "What gates the next one") must pass before the next milestone starts; closing the last issue is not enough. Do not close the GitHub milestone here; that is the manual `close-milestones.yml` workflow (its `scripts/close_milestones.py` title list may need the milestone added).
