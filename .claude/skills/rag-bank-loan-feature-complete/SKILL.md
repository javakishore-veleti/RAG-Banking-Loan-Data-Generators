---
name: rag-bank-loan-feature-complete
description: Completes a rag-bank-loan feature issue (`[Feature] F020 — …`) once all its stories are closed - writes the Done status line, and after Kishore approves, labels it done, closes it, ticks it in GIT_ISSUES_SEQUENCING.md, logs and commits, then refreshes the parent epic. Use when the user runs /rag-bank-loan-feature-complete N (optionally with dry-run).
disable-model-invocation: true
---

# rag-bank-loan-feature-complete

Input: feature issue number `N`, optional `dry-run`. Run `gh` from the repo root (it reads the repo from the git remote; never type owner/repo). Scratch files only in `runtime_data/tmp/`, never `/tmp`.

**dry-run:** read-only calls run as normal; every write is printed as `WOULD RUN: <command>` instead; the new body is still saved to `runtime_data/tmp/issue-N.md`; the approval stop is still shown and nothing after it runs.

1. Run `rag-bank-loan-progress-sync` on `N`. It maps each child ID in the body (`- **S047** …`) to its issue number and state and writes the `**Progress:**` line (in dry-run it only prints it).
2. If any story is not closed, stop and list them: `S047 #76, S048 #77 still open.` Change nothing and write no body file.
3. Read the feature ID (`F020`) from the title, the parent from `**Parent epic:** #E (E006)` and the milestone code from `**Milestone:** M003`.
4. Build the new body in `runtime_data/tmp/issue-N.md`: put `**Status:** Done — All T stories are done: S047 #76, S048 #77.` on its own line right after `**Type:**` (replace an existing `**Status:**` line). T is the story count; list stories in ID order.
5. **STOP for approval.** Show the close list (`#75 F020 — Shard marker & idempotency`), the new body, and the commands below. Wait for Kishore's explicit yes. Anything else: change nothing.
6. After yes, run in order:
   - `gh issue edit N --remove-label "status: in-progress" --add-label "status: done" --body-file runtime_data/tmp/issue-N.md` (ignore a "label not found" on remove).
   - `gh issue close N --reason completed`
   - In `GIT_ISSUES_SEQUENCING.md`, flip ⬜ → ✅ on that feature's heading only: `#### F020 #75 ⬜ …` → `#### F020 #75 ✅ …`.
   - `rag-bank-loan-milestone-log N`, only if `docs/Project_Management/Issues/Milestone_NNN.md` exists (NNN from M003). Never create it; if missing, say "no milestone log yet, skipped".
   - `rag-bank-loan-commit-push` with the message `M003: complete feature F020 #75`.
7. Run `rag-bank-loan-progress-sync` on epic `E`. If every feature of `E` is now closed, end with: "All features of #E (E006) are done. Run `/rag-bank-loan-epic-complete E`." Otherwise list the features still open.

Never close the epic or the milestone here.
