# S050 #80 — Dedup audit also checks description overlap (design)

**Story:** #80 S050 — Audit the *description* overlap too (see F013) — not just IDs.
**Feature:** #78 F021 — Post-run dedup audit. **Epic:** #6 E006. **Date:** 2026-11-15.
**Size:** small change (short design). Builds on S049 #79
(`Middleware/Workflows/Datagen/src/audit/dedup_audit.py`).

## Intent

S049's audit proves no natural key repeats. Two records with different keys can still have
near-identical descriptions, which makes RAG retrieval useless (DESIGN.md §5, F013). The
post-run audit must therefore also measure description overlap with the F013 metric and fail
a run above the M003 limits (`GIT_ISSUES_SEQUENCING.md` M003 exit criteria):
**wording-only mean ≤ 0.15** and **same loan-type pairs with Jaccard > 0.5 ≤ 5%**.

## What exists today

- F013 metric (`uniqueness_check.py`): Jaccard on word 5-gram shingles. Wording-only means
  digits are replaced (`re.sub(r"\d+", "#", text)`) and shingles keep letters only
  (`shingles(text, keep_numbers=False)`). `shingles` and `jaccard` are module-level functions.
  `uniqueness_check.py` measures freshly made records, not a run on disk.
- A run's `txt/<file>.txt` holds exactly the description text the metric uses
  (`"\n".join(lines_for(rec))`, written by `write_txt`). Each manifest row has `format`,
  `file` (relative to the manifest directory) and `loan_type`.
- Recon, 2026-11-15: generator `--count 200 --seed 7 --formats txt,csv` → wording-only mean
  0.104, same-type > 0.5 = 0.81% (19,900 pairs). Inside the limits.

## Approaches

1. **Read the run's txt documents (chosen).** For every `format == "txt"` row, read the file,
   compute the F013 wording-only shingles, compare every pair. Measures the run as written.
2. **Regenerate the records from seed/count** (as `uniqueness_check.py` does). That audits the
   generator, not the run, and the manifest does not record the seed. Rejected.
3. **Use manifest `question` + `answer` as the description.** Not the F013 text, so the numbers
   would not compare to the limits. Rejected.

Metric source: import `shingles` and `jaccard` from `uniqueness_check.py` (the Datagen root is
added to `sys.path`) instead of copying them, so there is one definition of the F013 metric.
`uniqueness_check.py` is not changed.
Decision (delegated by Kishore for this run): approach 1 with the import.

## Design

- New `Middleware/Workflows/Datagen/src/audit/description_audit.py`:
  - Constants `WORDING_MEAN_MAX = 0.15`, `SAME_TYPE_HIGH = 0.5`, `SAME_TYPE_PCT_MAX = 5.0`.
  - `load_descriptions(rows, base_dir) -> list[tuple[str, str]]` — `(loan_type, text)` for each
    txt row. A missing `file` or `loan_type` field, or an unreadable file, raises the S049
    `ManifestError`. No txt rows also raises it: the run must include txt to audit descriptions.
  - `overlap_metrics(descriptions) -> dict` with keys `descriptions`, `pairs`, `mean`,
    `same_type_pairs`, `same_type_high_pct`. Fewer than 2 descriptions → 0 pairs, mean 0.0.
  - `limit_failures(metrics) -> list[str]` — one message per limit exceeded. The limits are
    inclusive (`mean == 0.15` passes, `5.0%` passes).
- `dedup_audit.main` runs both checks and prints both results. Exit 0 only when there are no
  duplicate keys and no limit failures. Exit 1 on either. Exit 2 on bad input (as in S049,
  now including missing or unreadable txt documents and runs with no txt documents).
- Output adds `Description overlap: <n> descriptions, <pairs> pairs, wording-only mean=<m>
  (limit 0.15), same-type >0.5=<p>% (limit 5%)` and one `OVERLAP <message>` line per failure.

Non-goals: MinHash/LSH or sampling for 200k-record runs (O(n²) pairs: fine at M003 scale,
it is M005's problem); embedding similarity; changes to the generator or
`uniqueness_check.py`; Athena SQL for overlap (Jaccard is not a GROUP BY query).
Anti-goal: a check that passes because it measured nothing. No txt documents is exit 2,
not a pass.

## Acceptance

- [ ] B1 — The audit measures overlap with the F013 functions (`uniqueness_check.shingles` /
  `jaccard`, wording-only) on the run's own txt documents.
- [ ] B2 — A generated 200-record run (seed 7, `--formats txt,csv`) passes both limits; the CLI
  exits 0 and prints the measured mean and same-type percentage.
- [ ] B3 — A fixture of near-identical descriptions (same wording, different numbers, same
  loan type) fails; the CLI exits 1 and prints `OVERLAP` lines.
- [ ] B4 — Each limit is checked on its own: mean above 0.15 fails, same-type above 5% fails
  with a low mean, and values exactly at the limits pass.
- [ ] B5 — A run with no txt documents, or a missing txt file, exits 2 with a message.
- [ ] B6 — S049 behaviour is unchanged: the duplicate-key tests still pass, and duplicates
  alone still exit 1.
- [ ] B7 — No new dependencies; both suites pass and the new tests are collected.
