---
name: rag-bank-loan-progress-sync
description: Rebuilds the child list and Progress line of a rag-bank-loan feature or epic GitHub issue from the real state of its child issues, and sets the `status: in-progress` label when work has started. Use when a rag-bank-loan- skill says to run rag-bank-loan-progress-sync, or when a feature or epic child list looks stale.
---

# rag-bank-loan-progress-sync

Input: feature or epic issue number `P`, plus optional `dry-run`. Run `gh` from the repository root: it reads the repository from the git remote, so never type the owner or repository name. Scratch files go in `runtime_data/tmp/` only.

**dry-run:** every read-only `gh` call still runs. No write is done (`gh issue edit`, label changes): print each one as `WOULD RUN: <command>` instead. The new body is still saved to `runtime_data/tmp/issue-P.md`.

1. `gh issue view P --json title,body,labels`. The title must start with `[Feature]` or `[Epic]`, else stop.
2. Find the children (IDs are `S`/`F` + 3 digits):
   - Child lines: `- **S047** text`, or an already synced `- [ ] **S047** #76 text (planned)`. Strip any `[ ]`/`[x]`, `#C` and trailing `(done)`/`(in-progress)`/`(planned)` to get the ID and text back.
   - Epic with no child lines: take the `F…` IDs from its `Features:` sentence (for example `Features: F019 natural-hash, F020 markers`). If there is none, run `gh issue list --state all --label feature --limit 300 --json number,title,state,labels,body` once and keep the features whose `**Parent epic:**` is `#P`. The text of a new line is the child's title after ` — `.
   - No children: stop and say so.
3. For each ID: `gh issue list --state all --search "S047 in:title" --json number,title,state,labels,body`. Keep the result whose title key is exactly that ID (`[Story] S047 — …` / `[Feature] F019 — …`).
   - Not found: leave the line as it was, leave it out of the counts, and report it.
   - Its `**Parent feature:**` or `**Parent epic:**` is not `#P`: drop the line and report it.
4. Write each kept line as `- [x] **ID** #C text (done)` when closed, `- [ ] **ID** #C text (in-progress)` when open with label `status: in-progress`, else `- [ ] **ID** #C text (planned)`. Keep the text from the existing line. Lines stay in their original order and place; new epic lines go right after the `Features:` paragraph (or at the end of the body).
5. Remove any old `**Progress:**` line and put `**Progress:** D of T done — <state>` below the child list, after one blank line (without it the line renders as part of the last bullet). D counts done children, T counts kept children. State is `done` when D equals T, `in-progress` when D is above 0 or any child is in progress, otherwise `planned`. Change nothing else in the body: running this twice gives the same body.
6. Save the body to `runtime_data/tmp/issue-P.md`. If it differs from the current body, run `gh issue edit P --body-file runtime_data/tmp/issue-P.md`.
7. If the state is `in-progress` and `P` lacks the label, run `gh issue edit P --add-label "status: in-progress"`. Remove no labels. Never add `status: done` here: only `rag-bank-loan-feature-complete` and `rag-bank-loan-epic-complete` do that.
8. Report one line: `#P: D of T done`, plus any not-found or dropped children.
