# Datagen — synthetic banking-loan data generation (ETL)

This is the Datagen app. It generates a large, realistic, *unique*
synthetic corpus of banking-loan documents in six formats
(PDF, DOCX, XLSX, CSV, TXT, PNG) so a RAG system can be built,
tested, and measured against known ground truth.

**Scale:** 200,000 records per annum, last 10 years, per document
type (2M per format, 12M files total). Start small — 1,000 records.

## Layout (inside this folder)

```
.
├── Dockerfile, requirements.txt   # Batch worker image (<project>-worker)
├── src/
│   ├── generator/generator.py     # the generator (no AWS deps)
│   ├── planner/planner.py         # Lambda: split a run into SQS shards
│   └── worker/batch_worker.py     # Batch: poll SQS, generate, upload
├── infra/
│   ├── cloudformation/            # storage / compute / orchestration
│   ├── stepfunctions/             # state-machine.json
│   └── archive-terraform/         # superseded — reference only
├── scripts/    # run_local.sh, enqueue_shards.py (DLQ replay)
├── tests/      # generator unit tests
├── deployments/  # how this app's image + stacks are deployed
├── uniqueness_check.py, uniqueness_report.md
└── README.md
```

## Quick start (local, no AWS)

```bash
python3 src/generator/generator.py --count 10 --out ./corpus --year 2024
python3 uniqueness_check.py --count 200 --seed 7
```

## Real-artifact seeding (F016)

The generator's wording comes from real public loan documents, not
invented text:

- `data/seeds/SEEDS.md` — manifest of 21 fetched artifacts (RBI Master
  Directions, SBI / HDFC / ICICI / PNB / Bank of Baroda loan pages and
  MITC sheets, MUDRA / PMMY, IBA Model Education Loan Scheme, CFPB
  complaint data), each with its public URL and what was extracted.
- `data/seeds/terminology.yaml` — per loan type: sourced rate ranges,
  purposes, document checklists, terms and fees. Every entry carries
  the seed ID it came from.
- `src/generator/generator.py` loads the file at runtime (PyYAML if
  available, otherwise a built-in minimal parser — the Batch worker
  image has no PyYAML) and picks seed terms, documents and fees per
  record. If the file is missing, the generator falls back to its
  built-in terms and still works standalone.
- `tests/test_seed_terminology.py` checks the file loads for all 7 loan
  types, every term traces to a listed seed, generated descriptions
  contain seed terminology, and determinism still holds.

To refresh: fetch the source again, update the entry in `SEEDS.md`
(and the fetch date), change the affected entries in
`terminology.yaml`, then run the tests above plus
`python3 uniqueness_check.py --count 50 --seed 7`.

## Policy corpus (F018)

Policy documents are the other half of the corpus: one document =
one rule that applies to thousands of loans (rate policy, prepayment
rules, document checklists, fees, tenures, gold LTV caps), versioned
over time — not one document per loan.

- `src/policy/policy_generator.py` — dependency-free, deterministic,
  fixed set: 2 versions per loan type × 7 loan types = **66 policy
  documents** in all 6 formats, under
  `policy/<loan_type>/version=<version>/`, plus `policy/manifest.jsonl`
  (`record_kind: policy`).
- `src/policy/versions.py` — the version table (v2023-01, v2024-01;
  v2024-01 is latest), shared with the customer generator: every
  customer record carries the `policy_version` in force for its loan
  type in its start year, shown in its description lines and in
  `manifest.jsonl`.
- `data/policies/POLICIES.md` — manifest of the policy set: versions,
  what changed, and the seed ID each rule traces to.
- Rule text comes from the F016 seeds (`data/seeds/terminology.yaml`);
  a rule that cannot be traced to a fetched seed is omitted, not
  invented (business/MSME have no prepayment rule, auto has no fees
  rule). Both versions currently carry the same figures — only one
  fetch snapshot exists, so no historical figures were invented.
- `tests/test_policy_corpus.py` checks version uniqueness, exactly
  one latest per loan type, that every customer `policy_version`
  exists, determinism, and that every rule traces to a seed.
- Why policy docs are not generated at 200k/year: one rule applies
  to thousands of loans, so 200,000 copies would be duplicate content
  that drowns retrieval. See DESIGN.md §3.2.

To regenerate: `python3 src/policy/policy_generator.py --out ./policy-corpus`.
Policy docs are generated once, locally — the AWS upload wiring for
the `policy/` prefix is still to be done (see HANDOVER.md).

## Natural-hash dedup (F019)

Two records can carry identical business fields under different IDs,
and a surrogate PK (`doc_id`) cannot stop that. F019 adds an exact
duplicate guard:

- **Natural key (decided 2026-11-12 by the repo owner):** the full
  content — `(customer, loan_type, amount, rate, tenure, start_date)`.
  ("customer" is the customer name, stored as `name` in records.)
- **Hash:** `src/dedup/natural_hash.py` normalises the key fields
  (lowercase + trim, amounts to whole rupees, rates to 2 decimals,
  dates to ISO `YYYY-MM-DD`) and hashes them:
  `natural_hash = SHA256(fields joined by "|")`, 64-char lowercase hex.
  Every record from `make_record` carries `natural_hash`, and the
  generator's `manifest.jsonl` rows carry it too.
- **Claim:** before uploading, the Batch worker claims the hash in
  the DynamoDB dedup table (`<project>-dedup`, PK `natural_hash`)
  with `PutItem` + `ConditionExpression:
  attribute_not_exists(natural_hash)`. The first writer wins.
- **On conflict:** the record is a duplicate — the worker skips all
  of its files (no S3 upload, no manifest row) and logs
  `Skipped duplicate <loan_id> hash <hash>`. The table name comes
  from the `DEDUP_TABLE` env var; when it is unset, claiming is
  skipped so existing deployments keep working (add the var to the
  Batch job definition env to enable dedup).
- **What is NOT done:** S3 keys do not include the hash (DESIGN.md
  §6 step 5) — the atomic claim is the guard, so keys are unchanged.
  F020 (per-shard `.done` markers, deterministic keys) and F021
  (post-run duplicate audits) are still open.
- `tests/test_natural_hash.py` checks normalisation variants hash
  identically, different key fields hash differently, the claim lets
  the first writer win, and generator hashes are deterministic.

## Deployments

See `deployments/README.md`. In short: the image is built from
this folder as the Docker build context
(`docker build -f Dockerfile .`) by the
`aws-001-provision-infra.yml` workflow, pushed to ECR as
`<project>-worker`, and the CloudFormation stacks in `infra/`
are deployed by the same workflow. Data generation is triggered
manually, one workflow per format, via the root
`.github/workflows/generate-<format>.yml` files.

Full documentation lives at the repo root: `README.md`,
`ARCHITECTURE.md`, `DESIGN.md`, `GITHUB_ISSUES.md`.
