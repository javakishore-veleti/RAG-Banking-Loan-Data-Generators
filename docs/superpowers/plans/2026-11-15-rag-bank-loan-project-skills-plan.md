# Plan — `rag-bank-loan` project skills

Date: 2026-11-15 · Owner: Kishore · Status: **Approved 2026-11-15** — in progress
Design: `docs/superpowers/specs/2026-11-15-rag-bank-loan-project-skills-design.md` (approved)

Already done (2026-11-15): Superpowers 7.0.2 at project scope, `gh` 2.104.0 installed and
logged in, labels `status: in-progress` and `status: done` created, design pushed (`9b79877`).

## Rules for every task

- **Red → green.** Each task starts with a check that fails because the thing does not exist
  yet, then makes it pass. For a skill, "red" is the check command failing; "green" is the
  same command passing plus the dry run below.
- **No live issue edits while building.** Every skill that writes to GitHub takes a `dry-run`
  argument: it prints each `gh` command and the new issue body to `runtime_data/tmp/` instead
  of sending. All verification uses `dry-run` on real issue numbers (read-only).
- **Commit after each task** with `Skills: <summary>`, files staged by name, author Kishore,
  no co-author trailer (checked with `git log -1 --format='%an <%ae>%n%B'`), then push.
- No drive-by changes to other files.

## Task 1 — Confirm each tool's skill folder

Check the current docs of Claude Code, Cursor, GitHub Copilot (CLI + VS Code) and Codex for
the project skill folder each reads.

- Verify: write the table (tool → folder → doc URL) into design §4.1. Any tool that does not
  read project skills is dropped from the symlink list and noted there.
- Files: `docs/superpowers/specs/2026-11-15-rag-bank-loan-project-skills-design.md`

## Task 2 — Folder, symlink, scratch dir (revised after Task 1, see design §4.1)

- Red: `ls .claude/skills .agents/skills` fails.
- Create `.claude/skills/` (real folder) and the Codex link
  `ln -s ../.claude/skills .agents/skills`. Add `runtime_data/` to `.gitignore`.
- Green: `ls -l .agents` shows `skills -> ../.claude/skills`;
  `git check-ignore runtime_data/tmp/x` prints the path; `git ls-files -s .agents/skills`
  shows mode `120000`.
- Files: `.claude/skills/.gitkeep`, `.agents/skills`, `.gitignore`

## Task 3 — `rag-bank-loan-commit-push`

Port of `ccaa-commit-push`. Changes: `S047 #76:` / `M008:` / `Skills:` message forms; runs
the two `pytest` commands from `ci.yml` when Python under `Middleware/` changed; never
`git add -A`; never stage `runtime_data/`, `.env`, datasets, generated corpus files; author
check and trailer strip written for any tool (mandatory); push and confirm not ahead.

- Red: `test -f .claude/skills/rag-bank-loan-commit-push/SKILL.md` fails.
- Green: the file exists with `name` + `description` front matter; this task's own commit is
  made by following the skill, and `git log -1` shows Kishore as author and no trailer.
- Files: `.claude/skills/rag-bank-loan-commit-push/SKILL.md`

## Task 4 — `rag-bank-loan-progress-sync`

Rebuilds a feature's or epic's child list from the children's real state. This repo lists
children by ID (`- **S047** …`), so the skill maps IDs to issue numbers with
`gh issue list --search "S047 in:title"`, keeps the existing text, adds `(done)` /
`(in-progress)` / `(planned)` and a `**Progress:** D of T done — <state>` line, and sets the
`status: in-progress` label when D > 0 or any child is in progress. Never sets `status: done`.

- Red: file missing.
- Green: `dry-run` on feature **#75** (F020) shows `0 of 2 done — planned` with S047 → #76
  and S048 → #77; `dry-run` on epic **#6** shows `1 of 3 done` (F019 closed).
- Files: `.claude/skills/rag-bank-loan-progress-sync/SKILL.md`

## Task 5 — `rag-bank-loan-milestone-log` + milestone file template

Port of `ccaa-milestone-log` against `docs/Project_Management/Issues/Milestone_NNN.md`
(`M008` → `Milestone_008.md`). Same row format
`Issue | Step | Command | Status | Started | Completed`, same `begin` / advance logic.
Template gives the CCAA sections (build order, grouping, step table, skills, notes) with the
12-step story flow from design §1.

- Red: both files missing.
- Green: copy the template into `runtime_data/tmp/Milestone_999.md` with two fake story rows;
  run the skill's steps against it with `begin`, then advance twice; the rows show
  Planned → In progress → Done with times from `date '+%F %H:%M'`. Real milestone files are
  not created in this plan (design Q3).
- Files: `.claude/skills/rag-bank-loan-milestone-log/SKILL.md`,
  `docs/Project_Management/Issues/Milestone_TEMPLATE.md`

## Task 6 — `rag-bank-loan-story-start`

Port of `ccaa-story-start`. Checks `[Story]` in the title and that it is open; adds label
`status: in-progress`; adds or replaces a `**Status:** In progress — started …` line under
`**Type:**`; finds the feature from `**Parent feature:** #F` and the epic from the feature's
`**Parent epic:** #E`; moves them to in-progress; runs progress-sync on both; logs to the
milestone file if it exists; commit-push; replies with the next step of the 12-step flow.

- Red: file missing.
- Green: `dry-run 188` (S121) prints the label commands for #188, #187 (F047), #182 (E015)
  and the new #188 body with only the Status line added.
- Files: `.claude/skills/rag-bank-loan-story-start/SKILL.md`

## Task 7 — `rag-bank-loan-story-complete`

Port of `ccaa-story-complete`. Acceptance comes from the story's spec in
`docs/superpowers/specs/` (issues have no checklist); each item needs evidence; tests must
pass; story branch merged to `main` and pushed; commits found with `git log --grep="#N:"`.
Writes a ticked `**Acceptance:**` list and a `**Status:** Done — …` line, then **stops and
shows the close list**; only after Kishore says yes: label `status: done`, `gh issue close`,
flip the ID's ⬜ → ✅ in `GIT_ISSUES_SEQUENCING.md`, milestone-log, commit-push,
progress-sync on the feature.

- Red: file missing.
- Green: `dry-run` on closed story **#74** (S046) prints the would-be body, the commits found
  for `#74:` (none expected, since earlier commits did not use this form; the skill must
  say so, not fail), and the close-approval prompt; nothing is sent.
- Files: `.claude/skills/rag-bank-loan-story-complete/SKILL.md`

## Task 8 — `rag-bank-loan-feature-complete` and `rag-bank-loan-epic-complete`

Ports of the CCAA pair, with the same approval stop before closing and the ✅ flip in
`GIT_ISSUES_SEQUENCING.md`. Epic-complete also updates the milestone row in `HANDOVER.md` §2
and `GIT_ISSUES_SEQUENCING.md` status lines when the epic's milestone has no open items left.

- Red: files missing.
- Green: `dry-run` feature-complete on **#75** stops with "S047 #76, S048 #77 still open";
  `dry-run` epic-complete on **#5** (E005, all closed) reaches the approval prompt.
- Files: `.claude/skills/rag-bank-loan-feature-complete/SKILL.md`,
  `.claude/skills/rag-bank-loan-epic-complete/SKILL.md`

## Task 9 — Tool-neutral and discovery checks

- `grep -rniE 'cursor|claude|copilot|codex' .claude/skills/rag-bank-loan-*` returns only the one line about
  Claude Code's `/superpowers:` prefix.
- `grep -rn 'ccaa\|M02-\|local:api' .claude/skills` returns nothing.
- Claude Code: after `/reload-plugins`, the seven `rag-bank-loan-*` skills appear in the skill
  list. Other tools: Kishore opens the repo in Cursor once and confirms they are listed
  (the only check that needs him).

## Task 10 — Docs

- Add a short "Story workflow (Superpowers + rag-bank-loan skills)" section to `HANDOVER.md`
  §5-adjacent: the 12-step table, the dry-run rule, where skills live.
- Mark this plan and the design **Done** with the final commit hashes.
- Verify: `HANDOVER.md` diff contains only the new section.

## Estimated time

About 60–90 minutes of agent work across 10 small commits. The only steps that need Kishore:
approving this plan, the Cursor check in Task 9, and later any real close list.
