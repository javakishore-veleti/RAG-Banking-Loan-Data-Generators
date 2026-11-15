---
name: rag-bank-loan-story-start
description: Marks a rag-bank-loan GitHub story as started, moves its parent feature and epic to in-progress and refreshes their progress, then gives the next step of the 12-step story flow. Use when the user runs rag-bank-loan-story-start N before working on story issue N.
disable-model-invocation: true
---

# rag-bank-loan-story-start

Input: story issue number `N`, optionally `dry-run`. Run `gh` from the repository root: it reads the repository from the git remote, so never type the owner or repository name. Needs network access. Scratch files go in `runtime_data/tmp/` (git-ignored), never `/tmp`.

**dry-run:** read-only `gh` calls still run. Do not run any write (`gh issue edit`, label change, file edit outside `runtime_data/tmp/`, git commit or push): print each as `WOULD RUN: <command>`, still save the new body to `runtime_data/tmp/issue-N.md` and show its diff against the current body. Pass `dry-run` to every sibling skill you call.

1. `gh issue view N --json title,state,labels,body`. Stop and tell the user if the title does not start with `[Story]` or the issue is closed. Take the key (`S047`) from the title and the milestone (`M003`) from `**Milestone:**`.
2. Milestone gate (HANDOVER.md §2): M001 → M002 → M003 → M004 → M005, M006 → M007, M008 → M009 → M010. If the milestone before this one in its chain still has open issues (`gh api 'repos/{owner}/{repo}/milestones?state=all' --jq '.[] | "\(.title) \(.state) \(.open_issues)"'`; gh fills the placeholders), stop and warn the user; go on only if they say so.
3. Labels: `gh issue edit N --add-label "status: in-progress"`.
4. Body: put `**Status:** In progress — started YYYY-MM-DD HH:MM.` (time from `date '+%F %H:%M'`) on its own line right after the `**Type:**` line; replace an existing `**Status:**` line instead of adding a second. Change nothing else. Save to `runtime_data/tmp/issue-N.md`, then `gh issue edit N --body-file runtime_data/tmp/issue-N.md`.
5. Parents: `F` is the number in the story's `**Parent feature:** #F (…)`; `E` is the number in the feature's `**Parent epic:** #E (…)` (`gh issue view F --json body,labels`). For each of `F` and `E` that has neither `status: in-progress` nor `status: done`, run `gh issue edit <F or E> --add-label "status: in-progress"`.
6. Run `rag-bank-loan-progress-sync` on `F`, then on `E`.
7. Milestone log: if `docs/Project_Management/Issues/Milestone_NNN.md` exists (M008 → `Milestone_008.md`), run `rag-bank-loan-milestone-log N begin`, then `rag-bank-loan-milestone-log N` (step 1 done, step 2 starts), and `rag-bank-loan-milestone-log F begin` / `E begin` for each parent step 5 just moved. If the file is missing, skip this step and say so; never create it here.
8. Run `rag-bank-loan-commit-push N` with the summary `start story` (message `S047 #76: start story`).
9. Reply with the story title and the next step, step 2, with a one-line prompt built from the story text, e.g. `/brainstorming Story #N: <story sentence>`.

The 12 steps: 1 `rag-bank-loan-story-start N` · 2 brainstorming · 3 using-git-worktrees · 4 writing-plans · 5 test-driven-development · 6 subagent-driven-development (or executing-plans) · 7 `rag-bank-loan-commit-push N` after every task · 8 verification-before-completion · 9 requesting-code-review · 10 `rag-bank-loan-commit-push N` (review fixes) · 11 finishing-a-development-branch · 12 `rag-bank-loan-story-complete N`. Use systematic-debugging before changing code on an unexplained test failure. In Claude Code the Superpowers skills are invoked as `/superpowers:<name>`.

For the rest of this chat, after each workflow step of story `N` finishes (brainstorming, using-git-worktrees, writing-plans, test-driven-development, the final task of subagent-driven-development and its commit, verification-before-completion, requesting-code-review, the final `rag-bank-loan-commit-push N`, finishing-a-development-branch), run `rag-bank-loan-milestone-log N` before you suggest the next step.

The story's spec and plan go in `docs/superpowers/specs/` and `docs/superpowers/plans/`, named `YYYY-MM-DD-S047-<topic>-design.md` and `YYYY-MM-DD-S047-<topic>-plan.md`. The spec must have an `## Acceptance` list; `rag-bank-loan-story-complete` checks every item against it.

This step runs on `main`. The next steps run in the story's worktree and branch (using-git-worktrees creates both in `.worktrees/`).
