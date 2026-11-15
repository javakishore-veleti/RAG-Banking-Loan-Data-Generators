-- F021 / S049 #79 — post-run dedup audit on the F019 natural key.
--
-- Within one format, a natural key (natural_hash = SHA256 of the
-- normalised (customer, loan_type, amount, rate, tenure, start_date))
-- must appear once. Any row this query returns is a duplicate, even
-- when the duplicates carry different doc_id / loan_id values.
-- A clean run returns 0 rows.
--
-- Local: src/audit/dedup_audit.py runs this file verbatim on an
-- in-memory sqlite table `manifest` built from a run's manifest.jsonl.
-- Athena: create a Glue table named `manifest` (JSON SerDe) over the
-- run's manifests/<run_id>/ prefix with at least the columns
-- `format` and `natural_hash`, then run this query unchanged.
-- Plain ANSI SQL only: keep it runnable on both engines.
SELECT format, natural_hash, COUNT(*) AS duplicate_count
FROM manifest
GROUP BY format, natural_hash
HAVING COUNT(*) > 1
ORDER BY format, natural_hash
