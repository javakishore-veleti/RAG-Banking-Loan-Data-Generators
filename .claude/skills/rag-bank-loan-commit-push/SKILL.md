---
name: rag-bank-loan-commit-push
description: Commits and pushes rag-bank-loan work as the repo owner (Kishore), with no AI co-author trailer, after the Middleware tests pass. Use after every plan task or sub-task of a story, at the end of a story, after review fixes, and when asked to commit and push.
---

# rag-bank-loan-commit-push

Input: optional story issue number `N`, an optional summary or full message (`rag-bank-loan-commit-push 76 "start story"`, `rag-bank-loan-commit-push "M003: complete feature F020 #75"`), and optional `dry-run`. A full message (one that already starts with `S047 #76:`, `M003:` or `Skills:`) is used as is; a summary gets the prefix from step 4. Without `N`, use the story started in this conversation (`rag-bank-loan-story-start`); if there is none, ask which story it belongs to, or use the `M008:` / `Skills:` form below.

Commit small and often: one logical change per commit. Run every command from the repo root.

1. With `N`, read the key: `gh issue view N --json title`. The key is the `S047` after `[Story]` in the title.
2. `git status -s`. Stage only the files this change touched, by name. Never `git add -A` or `git add .`. Never stage `runtime_data/`, `.env*`, secrets or keys, datasets, or generated corpus output (the PDF/DOCX/XLSX/CSV/TXT/PNG files the generator writes, e.g. `corpus/`, `policy-corpus/`). Also stage, when modified: `docs/Project_Management/Issues/Milestone_NNN.md`, `GIT_ISSUES_SEQUENCING.md` and `HANDOVER.md` (the complete skills edit them), and the story's spec and plan in `docs/superpowers/specs/` and `docs/superpowers/plans/`.
3. If any Python under `Middleware/` changed, run the tests from `.github/workflows/ci.yml`:
   ```bash
   python -m pytest Middleware/Workflows/Datagen/tests/ -q
   python -m pytest Middleware/Workflows/DataIndexing/tests/ -q
   ```
   Use `python3` if `python` is not on the PATH. Install nothing: if a run fails because `pytest` or a package is missing, stop, name what is missing and the `pip install -r Middleware/Workflows/<Datagen|DataIndexing>/requirements.txt pytest` line from `ci.yml`, and ask Kishore before installing. On any test failure, stop: do not commit, report the failure.
4. Commit with a one-line message, no body:
   - story work: `S047 #76: <imperative summary>`
   - milestone work not tied to one story: `M008: <summary>`
   - workflow tooling (skills, docs for the skills): `Skills: <summary>`
5. The author must be the repo owner from `git config user.name` and `git config user.email` (check them). Never pass `--author` and never change `git config`.
6. Mandatory, whichever tool you are: check `git log -1 --format='%an <%ae>%n%B'`. If the body has a `Co-Authored-By`, `Co-authored-by` or any other AI trailer, rebuild the commit before pushing:
   ```bash
   NEW=$(git commit-tree "$(git rev-parse 'HEAD^{tree}')" -p HEAD^ -m "$(git log -1 --format=%s)")
   git update-ref "refs/heads/$(git branch --show-current)" "$NEW"
   ```
   Check the log again. The author must be the owner and the body must be the subject line only.
7. `git push origin "$(git branch --show-current)"`. If rejected, `git pull --rebase origin "$(git branch --show-current)"`, then push again.
8. Confirm with `git status -sb` that the branch is not ahead. Report the short hash and subject (`git log -1 --format='%h %s'`).

**dry-run:** run steps 1–3 for real (reads and tests), but do not stage, commit, rebuild or push. Print each instead as `WOULD RUN: <command>` (the `git add` with each file named, the `git commit -m "…"`, the push), and list any file you left out and why.
