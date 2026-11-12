# GitHub Issues Plan — Synthetic Data Generation Only

> Scope: synthetic data generation only. No RAG ingestion, chunking,
> embedding, vector store, retrieval, or UI. Those are a separate plan.
>
> **Totals: 5 milestones, 9 epics, 33 features, 85 stories = 127 issues**
> (milestones are GitHub milestones, not issues; epics/features/stories
> are all GitHub issues, linked parent → child).
>
> **How to use this in GitHub:**
> 1. Create the 5 milestones (M001–M005) in the repo.
> 2. Create the 9 epic issues, label `epic`, assign each to its milestone.
> 3. Create the 33 feature issues, label `feature`, link to their epic
>    (`Parent: #<epic>` in the body, or use GitHub Projects).
> 4. Create the 85 story issues, label `story`, link to their feature.
> 5. Work milestone by milestone. Do not start M004 (AWS) before M002/M003
>    are done locally — the cloud pipeline amplifies whatever the
>    local generator does, good or bad.
>
> **Labels to create:** `epic`, `feature`, `story`, plus topical labels
> per issue — `aws`, `s3`, `dynamodb`, `sqs`, `batch`, `lambda`,
> `step-functions`, `cloudformation`, `ecr`, `cloudwatch`,
> `cloudtrail`, `datagen-wf`, `github-actions`, `infra-setup`,
> `infra-destroy`, `data-delete`, `generator`,
> `format-pdf`, `format-docx`, `format-xlsx`, `format-csv`,
> `format-txt`, `format-png`, `manifest`, `partitioning`,
> `uniqueness`, `dedup`, `realism`, `testing`, `docs`,
> `observability`. Every issue gets its type label *and* its topical
> labels — e.g. F022 Storage stack is `feature, aws, cloudformation,
> infra-setup, s3`; F032 Destroy infra is `feature, infra-destroy,
> github-actions, cloudformation`; S080 (destroy workflow) is
> `story, infra-destroy, github-actions, cloudformation`. The mapping
> lives in `scripts/create_issues.py` (`EPIC_LABELS` / `FEATURE_LABELS`); stories inherit their feature's labels.

---

## Milestones (5)

| # | Milestone | Goal | Exit criteria |
|---|---|---|---|
| M001 | Foundation & Local Generator | Generator runs locally, one loan type, one format, deterministic | `generator.py --count 10` works; tests pass |
| M002 | Six Formats & Ground Truth | All six formats, same facts, manifest with Q&A | 10 records × 6 formats verified; manifest complete |
| M003 | Uniqueness & Realism | Descriptions are unique enough for RAG; seeded from real artifacts | Wording-only mean ≤ 0.15, same-type >0.5 ≤ 5% on 200 records |
| M004 | AWS Professional Pipeline | CloudFormation + GitHub Actions + Batch, per format, manual triggers | One format + one year (1,000 records) runs end to end in AWS |
| M005 | Scale & Hardening | 200k/year × 10 years, per format, with retry and dedup proven | 200k for one format + one year completes; DLQ empty; dedup audit clean; teardown + data deletion verified |

---

## Epics (9)

| # | Epic | Milestone | Features |
|---|---|---|---|
| E001 | Generator core & data model | M001 | F001–F003 |
| E002 | Six format writers | M002 | F004–F009 |
| E003 | Manifest & ground truth | M002 | F010–F012 |
| E004 | Uniqueness & overlap control | M003 | F013–F015 |
| E005 | Realism & real-artifact seeding | M003 | F016–F018 |
| E006 | Deduplication | M003–M005 | F019–F021 |
| E007 | CloudFormation infra | M004 | F022–F024, F031 |
| E008 | Batch execution & orchestration | M004 | F025–F027 |
| E009 | Quality, observability & release | M005 | F028–F030, F032–F033 |

---

## Features & Stories (33 features, 85 stories)

### E001 — Generator core & data model (M001)

**F001 — Record model & loan types**
- S001. Define the loan record schema (fields, types, required/optional).
- S002. Add the 7 loan types with amount / rate / tenure ranges.
- S003. Compute EMI from amount / rate / tenure (not random).

**F002 — Deterministic generation & seeding**
- S004. Seedable RNG: same seed + start + year = same records.
- S005. Sequential loan IDs, deterministic from seed + index.
- S006. CLI `--seed` / `--start` for sharding and resume.

**F003 — CLI & local run**
- S007. CLI `--count`, `--out`, `--formats` (subset support).
- S008. Local run with no AWS dependencies and a clear success message.

### E002 — Six format writers (M002)

**F004 — PDF writer**
- S009. Write a one-page PDF loan summary (hand-built PDF, no ReportLab dep).
- S010. Verify the PDF opens and its text extracts correctly.

**F005 — DOCX writer**
- S011. Write a DOCX loan summary (hand-built OOXML).
- S012. Verify the DOCX parses with `python-docx`.

**F006 — XLSX writer**
- S013. Write an XLSX with loan fields + 12-month EMI schedule.
- S014. Verify the XLSX parses with `openpyxl` (both sheets).

**F007 — CSV writer**
- S015. Write one loan record as a CSV row, with full Q&A.
- S016. Verify CSV round-trips (header, quoting, UTF-8).

**F008 — TXT writer**
- S017. Write the description as plain text.
- S018. Verify TXT is identical in content to the other formats' facts.

**F009 — PNG writer**
- S019. Render a loan summary card as a PNG (Pillow, with fallback).
- S020. Verify the PNG is a valid image and its text is OCR-legible.

### E003 — Manifest & ground truth (M002)

**F010 — Manifest JSONL**
- S021. Write `manifest.jsonl`: one row per file, with question + answer.
- S022. Manifest row schema is documented and versioned (see DESIGN.md §7).

**F011 — S003 partitioning yyyy/mm/dd**
- S023. S003 keys use `raw/<format>/year=YYYY/month=MM/day=DD/` by loan start date.
- S024. Partition fields (`year`, `month`, `day`) are also in the manifest row.

**F012 — Year-based runs**
- S025. CLI / planner `--year` flag: start dates fall inside that year.
- S026. One run = one format + one year (200k/year target).

### E004 — Uniqueness & overlap control (M003)

**F013 — Overlap measurement**
- S027. Build `Middleware/Workflows/Datagen/uniqueness_check.py`: wording-only 5-gram Jaccard, with/without numbers.
- S028. Report mean / median / p90 / max and % pairs > 0.5 / > 0.8, overall and same-type.
- S029. Record the baseline (v1) numbers in `uniqueness_report.md`.

**F014 — Paraphrase & layout variants**
- S030. Four paraphrase variants per answer topic, chosen per record.
- S031. Three layouts + varied field labels + one contextual sentence per record.
- S032. Re-measure: wording-only mean and same-type >0.5 must improve vs baseline.

**F015 — Reject / regenerate loop**
- S033. Add `--max-overlap` to the generator CLI (default 0.65).
- S034. Generate → measure → reject/regenerate, up to 5 attempts per record.
- S035. Log how many descriptions were rejected/regenerated per run.

### E005 — Realism & real-artifact seeding (M003)

**F016 — Real artifact seeding**
- S036. Collect 20+ real public artifacts (blank loan forms, MITC sheets, RBI Master Directions, CFPB complaints) as seed templates.
- S037. Extract real terminology, rate ranges, and document checklists from the seeds.
- S038. Generator templates use the seed terminology, not invented wording.

**F017 — Realistic distributions**
- S039. Amounts use log-uniform (clustered) ranges per loan type, not uniform random.
- S040. Rates, tenures, and credit scores use realistic ranges per loan type.

**F018 — Policy corpus (small, versioned)**
- S041. Design a separate, small policy corpus (tens of docs, versioned by effective date).
- S042. Customer records reference a policy version (e.g. `home-v2024-01`).
- S043. Policy docs are *not* generated at 200k/year — document why in DESIGN.md.

### E006 — Deduplication (M003–M005)

**F019 — Natural-hash dedup**
- S044. Define the business natural key (confirm the unique field set with the owner).
- S045. Compute `natural_hash = SHA256(normalised unique fields)` in the generator/worker.
- S046. Claim the hash atomically in the dedup table (`attribute_not_exists`); skip on conflict.

**F020 — Shard marker & idempotency**
- S047. Each shard writes a `.done` marker; replay skips finished shards.
- S048. Deterministic S003 keys + DynamoDB upserts with identical values on retry.

**F021 — Post-run dedup audit**
- S049. Athena/Glue audit: `GROUP BY <unique fields> HAVING COUNT(*) > 1` must return 0 rows.
- S050. Audit the *description* overlap too (see F013) — not just IDs.

### E007 — CloudFormation infra (M004)

**F022 — Storage stack**
- S051. CloudFormation `storage.yaml`: S003 bucket, DynamoDB manifest + dedup, SQS FIFO + DLQ.
- S052. S003 versioning, encryption, and Intelligent-Tiering lifecycle.
- S053. Outputs are exported for the other stacks (`Fn::ImportValue`).

**F023 — Compute stack**
- S054. CloudFormation `compute.yaml`: ECR, Batch Fargate Spot, job queue + definition.
- S055. VPC / subnets / security groups come from GitHub Secrets as parameters.
- S056. Batch task role is least-privilege (S003, DynamoDB, SQS, logs only).

**F024 — Orchestration stack**
- S057. CloudFormation `orchestration.yaml`: Planner Lambda, Step Functions, DLQ alarm.
- S058. Planner Lambda code is packaged and uploaded by the provision workflow.
- S059. Step Functions definition is the single source of truth (mirrored in `Middleware/Workflows/Datagen/infra/stepfunctions/`).

**F031 — CloudTrail audit logging (infra provisioning, added)**
- S077. Enable CloudTrail in the infra stack: every AWS API call is logged (who provisioned, who started a run, who deleted what).
- S078. CloudTrail logs go to a separate, versioned S003 bucket with log-file validation enabled.
- S079. Verify the trail: after a provision + generate run, the trail contains the CloudFormation, Batch, SQS, and S003 calls for that run.

### E008 — Batch execution & orchestration (M004)

**F025 — Per-format manual workflows**
- S060. Six manual `workflow_dispatch` workflows, one per format, thin wrappers only.
- S061. One shared reusable workflow (`aws-002-generate.yml`) that all six call.
- S062. Each workflow takes `count`, `year`, `shard_size`, `seed` as inputs.

**F026 — Planner & SQS**
- S063. Planner Lambda splits a run into shards (10k records each) and enqueues them.
- S064. SQS FIFO dedup (`run_id + shard_id`) and redrive policy (3 → DLQ).
- S065. Planner input/output schemas are documented (DESIGN.md §7).

**F027 — Batch worker & retry**
- S066. Batch worker polls SQS, generates a shard, uploads to S003 + DynamoDB.
- S067. Three-layer retry: Step Functions → Batch (3×) → SQS (3× → DLQ).
- S068. DLQ replay script (`Middleware/Workflows/Datagen/scripts/enqueue_shards.py`) moves failed shards back to the main queue.

### E009 — Quality, observability & release (M005)

**F028 — Observability & alarms**
- S069. CloudWatch Logs for Batch + Lambda; DLQ depth alarm fires on > 0.
- S070. Run verification: S003 count + DynamoDB count by `run_id` must match the requested count.

**F029 — Testing & CI**
- S071. Unit tests for the generator (EMI, determinism, record fields).
- S072. CI workflow runs tests + `py_compile` on push/PR, with no AWS access.
- S073. Uniqueness check runs after any generator change (regression gate).

**F030 — Release & docs**
- S074. Detailed README.md, ARCHITECTURE.md, DESIGN.md are current for the release.
- S075. Release checklist: 1,000-record AWS run passes before any 200k run.
- S076. Cost measurement: time + vCPU-hours + S003 size for one 10k shard, recorded before scaling.

**F032 — Destroy infra / teardown (GitHub Actions, end of life)**
- S080. Add a manual `aws-010-destroy-infra.yml` GitHub Actions workflow (workflow_dispatch, with a typed confirmation input — never auto-run, never on push).
- S081. Teardown deletes the CloudFormation stacks in reverse order: orchestration → compute → storage, and deletes ECR images first so the compute stack can delete.
- S082. Verify after teardown: no stacks, no ECR repo, no Batch resources, no Lambda / Step Functions left; record the check in the run log.

**F033 — Delete the data (GitHub Actions, end of life)**
- S083. Add a manual `aws-009-delete-data.yml` GitHub Actions workflow (workflow_dispatch, with a typed confirmation input) that empties the S003 corpus bucket first — CloudFormation cannot delete a non-empty bucket.
- S084. Delete the DynamoDB manifest + dedup tables, SQS queues, and CloudTrail log bucket contents as part of the same cleanup, in the right order.
- S085. Verify after deletion: S003 bucket empty / deleted, tables gone, no charges continue; CloudWatch + CloudTrail are the last things removed, so the deletion itself is audited.

---

## Summary table

| Level | Count |
|---|---|
| Milestones | 5 |
| Epics | 9 |
| Features | 33 |
| Stories | 85 |
| **Total issues** | **127** |

## Suggested order

M001 → M002 → M003 → M004 → M005. Do not start M004 before M003 is done — the
cloud pipeline amplifies whatever the local generator does, good or
bad. In particular, do not scale to 200k/year (M005) until the
uniqueness numbers in M003 and the dedup audit in F021 are clean.
