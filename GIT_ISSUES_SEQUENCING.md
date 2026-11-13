# GitHub Issues Sequencing — RAG Banking Loan Corpus

This is the **execution order (sequencing)**, not a sort. Read it top to
bottom: M001 first, M010 last. Inside a milestone, work epic by epic, then
feature by feature, then story by story — always in ID order
(E001 → E019, F001 → F064, S001 → S165). The IDs **are** the sequence:
GitHub sorts issues by created or updated date, not by execution order,
so the IDs are what tell you what comes next.

Each line shows the GitHub issue number (#), the ID, the title, and the
status: ✅ closed (done) or ⬜ open (still to do). Status was checked
against GitHub on 2026-11-12 evening. **This file is a snapshot — GitHub
is the source of truth.** Update it when a milestone closes.

A closed item is done. The next **open** item in order is the next thing
to do. Do not skip ahead to a later milestone until the current one's
exit criteria pass (see "The gates between milestones" at the end).

## Table of Contents

- [How sequencing works](#how-sequencing-works)
- [M001: Foundation and Local Generator](#m001-foundation-and-local-generator)
- [M002: Six Formats and Ground Truth](#m002-six-formats-and-ground-truth)
- [M003: Uniqueness and Realism](#m003-uniqueness-and-realism)
- [M004: AWS Professional Pipeline](#m004-aws-professional-pipeline)
- [M005: Scale and Hardening](#m005-scale-and-hardening)
- [M006: Indexing Foundation and Pipeline](#m006-indexing-foundation-and-pipeline)
- [M007: Indexes, Quality and Hardening](#m007-indexes-quality-and-hardening)
- [M008: Local Development Platform](#m008-local-development-platform)
- [M009: Entitlements API Service](#m009-entitlements-api-service)
- [M010: Microservice Images, Pattern and Portals](#m010-microservice-images-pattern-and-portals)
- [The gates between milestones](#the-gates-between-milestones)

## How sequencing works

1. **Milestones run in order:** M001 → M002 → M003 → M004 → M005, then
   M006 → M007 for indexing, then M008 → M009 → M010 for API Services
   and the local platform. Indexing builds on the generated corpus, so
   M006 needs documents to exist before it can index them.
2. **Inside a milestone, epics run in ID order.** Inside an epic,
   features run in ID order. Inside a feature, stories run in ID order.
3. **A feature is done when all its stories are closed.** A milestone is
   done when its exit criteria pass (listed at the top of each section),
   not merely when its last story closes.
4. **To find any issue in GitHub:** search its ID (for example `S044`)
   in the repo search bar, or open it directly at
   `github.com/javakishore-veleti/RAG-Banking-Loan-Data-Generators/issues/<number>`.
5. **To see one milestone in GitHub:** Issues → Milestones → click the
   milestone, or search `is:issue milestone:M003`.

## M001: Foundation and Local Generator

Status: **Closed — 12 of 12**. Goal: generator runs locally, one loan type,
one format, deterministic. Exit criteria: `generator.py --count 10` works;
tests pass.

### E001 #1 ✅ Generator core and data model

#### F001 #10 ✅ Record model and loan types

1. S001 #11 ✅ Define the loan record schema (fields, types, required/optional).
2. S002 #12 ✅ Add the 7 loan types with amount / rate / tenure ranges.
3. S003 #13 ✅ Compute EMI from amount / rate / tenure (not random).

#### F002 #14 ✅ Deterministic generation and seeding

1. S004 #15 ✅ Seedable RNG: same seed + start + year = same records.
2. S005 #16 ✅ Sequential loan IDs, deterministic from seed + index.
3. S006 #17 ✅ CLI --seed / --start for sharding and resume.

#### F003 #18 ✅ CLI and local run

1. S007 #19 ✅ CLI --count, --out, --formats (subset support).
2. S008 #20 ✅ Local run with no AWS dependencies and a clear success message.

## M002: Six Formats and Ground Truth

Status: **Closed — 29 of 29**. Goal: all six formats, same facts, manifest
with Q&A. Exit criteria: 10 records × 6 formats verified; manifest complete.

### E002 #2 ✅ Six format writers

#### F004 #21 ✅ PDF writer

1. S009 #22 ✅ Write a one-page PDF loan summary (hand-built PDF, no ReportLab dep).
2. S010 #23 ✅ Verify the PDF opens and its text extracts correctly.

#### F005 #24 ✅ DOCX writer

1. S011 #25 ✅ Write a DOCX loan summary (hand-built OOXML).
2. S012 #26 ✅ Verify the DOCX parses with python-docx.

#### F006 #27 ✅ XLSX writer

1. S013 #28 ✅ Write an XLSX with loan fields + 12-month EMI schedule.
2. S014 #29 ✅ Verify the XLSX parses with openpyxl (both sheets).

#### F007 #30 ✅ CSV writer

1. S015 #31 ✅ Write one loan record as a CSV row, with full Q&A.
2. S016 #32 ✅ Verify CSV round-trips (header, quoting, UTF-8).

#### F008 #33 ✅ TXT writer

1. S017 #34 ✅ Write the description as plain text.
2. S018 #35 ✅ Verify TXT is identical in content to the other formats' facts.

#### F009 #36 ✅ PNG writer

1. S019 #37 ✅ Render a loan summary card as a PNG (Pillow, with fallback).
2. S020 #38 ✅ Verify the PNG is a valid image and its text is OCR-legible.

### E003 #3 ✅ Manifest and ground truth

#### F010 #39 ✅ Manifest JSONL

1. S021 #40 ✅ Write manifest.jsonl: one row per file, with question + answer.
2. S022 #41 ✅ Manifest row schema is documented and versioned (DESIGN.md §7).

#### F011 #42 ✅ S3 partitioning yyyy/mm/dd

1. S023 #43 ✅ S3 keys use raw/<format>/year=YYYY/month=MM/day=DD/ by loan start date.
2. S024 #44 ✅ Partition fields (year, month, day) are also in the manifest row.

#### F012 #45 ✅ Year-based runs

1. S025 #46 ✅ CLI / planner --year flag: start dates fall inside that year.
2. S026 #47 ✅ One run = one format + one year (200k/year target).
## M003: Uniqueness and Realism

Status: **Open — 7 open, 29 closed (36 total)**. Goal: descriptions are
unique enough for RAG; seeded from real artifacts. Exit criteria:
wording-only mean ≤ 0.15, same-type > 0.5 ≤ 5% on 200 records.

### E004 #4 ✅ Uniqueness and overlap control

#### F013 #48 ✅ Overlap measurement

1. S027 #49 ✅ Build uniqueness_check.py: wording-only 5-gram Jaccard, with/without numbers.
2. S028 #50 ✅ Report mean / median / p90 / max and % pairs > 0.5 / > 0.8, overall and same-type.
3. S029 #51 ✅ Record the baseline (v1) numbers in uniqueness_report.md.

#### F014 #52 ✅ Paraphrase and layout variants

1. S030 #53 ✅ Four paraphrase variants per answer topic, chosen per record.
2. S031 #54 ✅ Three layouts + varied field labels + one contextual sentence per record.
3. S032 #55 ✅ Re-measure: wording-only mean and same-type > 0.5 must improve vs baseline.

#### F015 #56 ✅ Reject / regenerate loop

1. S033 #57 ✅ Add --max-overlap to the generator CLI (default 0.65).
2. S034 #58 ✅ Generate → measure → reject/regenerate, up to 5 attempts per record.
3. S035 #59 ✅ Log how many descriptions were rejected/regenerated per run.

### E005 #5 ✅ Realism and real-artifact seeding

#### F016 #60 ✅ Real artifact seeding

1. S036 #61 ✅ Collect 20+ real public artifacts (blank loan forms, MITC sheets, RBI Master Directions, CFPB complaints) as seed templates.
2. S037 #62 ✅ Extract real terminology, rate ranges, and document checklists from the seeds.
3. S038 #63 ✅ Generator templates use the seed terminology, not invented wording.

#### F017 #64 ✅ Realistic distributions

1. S039 #65 ✅ Amounts use log-uniform (clustered) ranges per loan type, not uniform random.
2. S040 #66 ✅ Rates, tenures, and credit scores use realistic ranges per loan type.

#### F018 #67 ✅ Policy corpus (small, versioned)

1. S041 #68 ✅ Design a separate, small policy corpus (tens of docs, versioned by effective date).
2. S042 #69 ✅ Customer records reference a policy version (e.g. home-v2024-01).
3. S043 #70 ✅ Policy docs are *not* generated at 200k/year — document why in DESIGN.md.

### E006 #6 ⬜ Deduplication

All E006 issues sit in M003. The plan lists this epic as "M003–M005"
because the capability is *proven* across three phases: F019 defines the
key and hash here in M003, F020's markers only get exercised when runs
execute in AWS (M004), and the F021 audit only passes at scale (M005).
See HANDOVER.md §2 for the full explanation.

#### F019 #71 ✅ Natural-hash dedup

1. S044 #72 ✅ Define the business natural key (confirm the unique field set with the owner).
2. S045 #73 ✅ Compute natural_hash = SHA256(normalised unique fields) in the generator/worker.
3. S046 #74 ✅ Claim the hash atomically in the dedup table (attribute_not_exists); skip on conflict.

#### F020 #75 ⬜ Shard marker and idempotency

1. S047 #76 ⬜ Each shard writes a .done marker; replay skips finished shards.
2. S048 #77 ⬜ Deterministic S3 keys + DynamoDB upserts with identical values on retry.

#### F021 #78 ⬜ Post-run dedup audit

1. S049 #79 ⬜ Athena/Glue audit: GROUP BY <unique fields> HAVING COUNT(*) > 1 must return 0 rows.
2. S050 #80 ⬜ Audit the *description* overlap too (see F013) — not just IDs.

## M004: AWS Professional Pipeline

Status: **Open — 30 open, 0 closed**. Goal: CloudFormation + GitHub Actions
+ Batch, per format, manual triggers. Exit criteria: one format + one year
(1,000 records) runs end to end in AWS.

### E007 #7 ⬜ CloudFormation infra

#### F022 #81 ⬜ Storage stack

1. S051 #82 ⬜ CloudFormation storage.yaml: S3 bucket, DynamoDB manifest + dedup, SQS FIFO + DLQ.
2. S052 #83 ⬜ S3 versioning, encryption, and Intelligent-Tiering lifecycle.
3. S053 #84 ⬜ Outputs are exported for the other stacks (Fn::ImportValue).

#### F023 #85 ⬜ Compute stack

1. S054 #86 ⬜ CloudFormation compute.yaml: ECR, Batch Fargate Spot, job queue + definition.
2. S055 #87 ⬜ VPC / subnets / security groups come from GitHub Secrets as parameters.
3. S056 #88 ⬜ Batch task role is least-privilege (S3, DynamoDB, SQS, logs only).

#### F024 #89 ⬜ Orchestration stack

1. S057 #90 ⬜ CloudFormation orchestration.yaml: Planner Lambda, Step Functions, DLQ alarm.
2. S058 #91 ⬜ Planner Lambda code is packaged and uploaded by the provision workflow.
3. S059 #92 ⬜ Step Functions definition is the single source of truth (mirrored in Middleware/Workflows/Datagen/infra/stepfunctions/).

#### F031 #93 ⬜ CloudTrail audit logging

1. S077 #94 ⬜ Enable CloudTrail in the infra stack: every AWS API call is logged (who provisioned, who started a run, who deleted what).
2. S078 #95 ⬜ CloudTrail logs go to a separate, versioned S3 bucket with log-file validation enabled.
3. S079 #96 ⬜ Verify the trail: after a provision + generate run, the trail contains the CloudFormation, Batch, SQS, and S3 calls for that run.

### E008 #8 ⬜ Batch execution and orchestration

#### F025 #97 ⬜ Per-format manual workflows

1. S060 #98 ⬜ Six manual workflow_dispatch workflows, one per format, thin wrappers only.
2. S061 #99 ⬜ One shared reusable workflow (aws-002-generate.yml) that all six call.
3. S062 #100 ⬜ Each workflow takes count, year, shard_size, seed as inputs.

#### F026 #101 ⬜ Planner and SQS

1. S063 #102 ⬜ Planner Lambda splits a run into shards (10k records each) and enqueues them.
2. S064 #103 ⬜ SQS FIFO dedup (run_id + shard_id) and redrive policy (3 → DLQ).
3. S065 #104 ⬜ Planner input/output schemas are documented (DESIGN.md §7).

#### F027 #105 ⬜ Batch worker and retry

1. S066 #106 ⬜ Batch worker polls SQS, generates a shard, uploads to S3 + DynamoDB.
2. S067 #107 ⬜ Three-layer retry: Step Functions → Batch (3×) → SQS (3× → DLQ).
3. S068 #108 ⬜ DLQ replay script (Middleware/Workflows/Datagen/scripts/enqueue_shards.py) moves failed shards back to the main queue.
## M005: Scale and Hardening

Status: **Open — 20 open, 0 closed**. Goal: 200k/year × 10 years, per format,
with retry and dedup proven. Exit criteria: 200k for one format + one year
completes; DLQ empty; dedup audit clean; teardown + data deletion verified.

### E009 #9 ⬜ Quality, observability and release

#### F028 #109 ⬜ Observability and alarms

1. S069 #110 ⬜ CloudWatch Logs for Batch + Lambda; DLQ depth alarm fires on > 0.
2. S070 #111 ⬜ Run verification: S3 count + DynamoDB count by run_id must match the requested count.

#### F029 #112 ⬜ Testing and CI

1. S071 #113 ⬜ Unit tests for the generator (EMI, determinism, record fields).
2. S072 #114 ⬜ CI workflow runs tests + py_compile on push/PR, with no AWS access.
3. S073 #115 ⬜ Uniqueness check runs after any generator change (regression gate).

#### F030 #116 ⬜ Release and docs

1. S074 #117 ⬜ Detailed README.md, ARCHITECTURE.md, DESIGN.md are current for the release.
2. S075 #118 ⬜ Release checklist: 1,000-record AWS run passes before any 200k run.
3. S076 #119 ⬜ Cost measurement: time + vCPU-hours + S3 size for one 10k shard, recorded before scaling.

#### F032 #120 ⬜ Destroy infra / teardown

1. S080 #121 ⬜ Add a manual aws-010-destroy-infra.yml GitHub Actions workflow (workflow_dispatch, with a typed confirmation input — never auto-run, never on push).
2. S081 #122 ⬜ Teardown deletes the CloudFormation stacks in reverse order: orchestration → compute → storage, and deletes ECR images first so the compute stack can delete.
3. S082 #123 ⬜ Verify after teardown: no stacks, no ECR repo, no Batch resources, no Lambda / Step Functions left; record the check in the run log.

#### F033 #124 ⬜ Delete the data

1. S083 #125 ⬜ Add a manual aws-009-delete-data.yml GitHub Actions workflow (workflow_dispatch, with a typed confirmation input) that empties the S3 corpus bucket first — CloudFormation cannot delete a non-empty bucket.
2. S084 #126 ⬜ Delete the DynamoDB manifest + dedup tables, SQS queues, and CloudTrail log bucket contents as part of the same cleanup, in the right order.
3. S085 #127 ⬜ Verify after deletion: S3 bucket empty / deleted, tables gone, no charges continue; CloudWatch + CloudTrail are the last things removed, so the deletion itself is audited.

## M006: Indexing Foundation and Pipeline

Status: **Open — 14 open, 16 closed (30 total)**. Goal: indexer runs locally,
one format, metadata + vectors land in pgvector. Exit criteria: local
dry-run + unit tests pass; one format indexed end to end in AWS (100 docs).

### E010 #128 ✅ Indexing core and metadata

#### F034 #133 ✅ Document loading per format

1. S086 #134 ✅ Extract text from PDF (pypdf) and DOCX (python-docx).
2. S087 #135 ✅ Extract text from XLSX (openpyxl) and CSV rows.
3. S088 #136 ✅ TXT loads as-is; PNG falls back to the manifest ground-truth description.

#### F035 #137 ✅ Chunking 500/100

1. S089 #138 ✅ Recursive splitter, 500 tokens / 100 overlap (2000/400 chars), separators "\n\n, \n, ". ", " ".
2. S090 #139 ✅ Overlap preserves text with no loss; short documents yield one chunk.

#### F036 #140 ✅ Metadata enrichment

1. S091 #141 ✅ Metadata schema: doc_id, loan_id, loan_type, format, year, policy_version, latest, page_hint, source_s3_key, embedding_model, indexed_at.
2. S092 #142 ✅ latest flag = newest version per loan_id (max year); policy_version recorded per chunk.
3. S093 #143 ✅ Deterministic chunk ids: sha1(doc_id:chunk_index:model_slug); different model → different id.

### E011 #129 ⬜ Embeddings and Bedrock

#### F037 #144 ⬜ Bedrock embedder

1. S094 #145 ⬜ Invoke Bedrock embedding model per chunk batch; record model actually used.
2. S095 #146 ⬜ Throttling retries with exponential backoff + jitter (5 attempts).
3. S096 #147 ⬜ Fail over to the default model once on AccessDenied/Validation/NotFound.

#### F038 #148 ✅ Embedding model config

1. S097 #149 ✅ config/embedding_models.yaml: default_model amazon.titan-embed-text-v2:0, per-format overrides (null = default).
2. S098 #150 ✅ Resolution order: workflow input → per-format override → default.
3. S099 #151 ✅ Dimensions table for known models; probe_dimensions for unknown models.

### E012 #130 ⬜ Vector and keyword indexes

#### F039 #152 ⬜ pgvector schema

1. S100 #153 ⬜ documents + chunks tables with metadata indexes.
2. S101 #154 ⬜ One chunk_embeddings_<model slug> table per model, HNSW index (vector_cosine_ops).
3. S102 #155 ⬜ vector_search with metadata filters (loan_type, year, latest).

#### F040 #156 ⬜ OpenSearch BM25 (optional)

1. S103 #157 ⬜ OpenSearch Serverless collection + index loan-chunks-bm25 behind EnableOpenSearch.
2. S104 #158 ⬜ Best-effort dual-write; opensearch_synced flags unsynced rows.
3. S105 #159 ⬜ Unsynced rows retried on the next run.
## M007: Indexes, Quality and Hardening

Status: **Open — 18 open, 5 closed (23 total)**. Goal: all six formats
indexed, retry/failover proven, teardown verified. Exit criteria: all
formats indexed for one year; DLQ empty; re-run idempotent; teardown +
data deletion verified.

### E013 #131 ⬜ Execution and orchestration

#### F041 #160 ⬜ Index planner Lambda

1. S106 #161 ⬜ List raw/<fmt>/year=YYYY/ keys from S3 and shard them (default 100 docs/shard).
2. S107 #162 ⬜ FIFO SQS dedup id = run_id-shard_id; .done markers per shard.

#### F042 #163 ⬜ Batch index worker

1. S108 #164 ⬜ Poll SQS one message at a time; index a whole shard, then delete the message.
2. S109 #165 ⬜ Any document failure fails the shard → SQS redrive 3x → DLQ; re-run upserts (idempotent).

#### F043 #166 ⬜ Step Functions and workflows

1. S110 #167 ⬜ AWS-Index-001 provision: indexing + orchestration stacks, reuses AWS-001 VPC by default.
2. S111 #168 ⬜ AWS-Index-002 reusable + AWS-Index-003…008 per-format wrappers.
3. S112 #169 ⬜ AWS-Index-009 delete index data + AWS-Index-010 destroy (typed confirmations; shared VPC untouched).

#### F044 #170 ⬜ Retry and failover

1. S113 #171 ⬜ SQS redrive 3x → DLQ, Batch retry 3x, Step Functions retries on failed shards.
2. S114 #172 ⬜ Idempotent re-runs: deterministic chunk ids + .done markers; no duplicates on retry.
3. S115 #173 ⬜ RDS Multi-AZ option (multi_az input, default false for learning).

### E014 #132 ⬜ Quality, observability and release

#### F045 #174 ⬜ Testing and evaluation

1. S116 #175 ✅ Unit tests: chunker, enricher, embedding config, retry, loader (8 tests).
2. S117 #176 ✅ Local dry-run: run_local.sh tests + L0–L2 dry-run with no AWS.
3. S118 #177 ⬜ Golden-set retrieval check: index a small set, verify known answers are found (pgvector).

#### F046 #178 ✅ Docs and release

1. S119 #179 ✅ README §15, ARCHITECTURE §15, DESIGN §16 + decision log updated.
2. S120 #180 ✅ CI runs indexer tests + py_compile; GITHUB_ISSUES_INDEXING.md plan + create-index-issues workflow in repo.

## M008: Local Development Platform

Status: **Open — 26 open, 0 closed (26 total)**. Goal: all local infra runs with one command; Python toolchain is uv. Exit criteria: docker-all-up brings up Postgres, Redis, ELK, RabbitMQ; status shows all healthy; package.json container commands work.

### E015 #182 ⬜ Local container platform

#### F047 #187 ⬜ Postgres via docker-compose

1. S121 #188 ⬜ Postgres docker-compose.yaml: port, volume, healthcheck.
2. S122 #189 ⬜ Multiple schemas in one server (postgres/postgres); schema-per-service convention.
3. S123 #190 ⬜ Postgres reachable from host and containers.

#### F048 #191 ⬜ Redis via docker-compose

1. S124 #192 ⬜ Redis docker-compose.yaml: persistence, port, healthcheck.
2. S125 #193 ⬜ Redis reachable from FastAPI services.

#### F049 #194 ⬜ ELK via docker-compose

1. S126 #195 ⬜ ELK docker-compose.yaml: Elasticsearch single-node + Kibana.
2. S127 #196 ⬜ Logstash pipeline receives application logs.
3. S128 #197 ⬜ Kibana shows service logs.

#### F050 #198 ⬜ RabbitMQ via docker-compose

1. S129 #199 ⬜ RabbitMQ docker-compose.yaml: management UI, port, healthcheck.
2. S130 #200 ⬜ Queue / exchange naming conventions documented.

#### F051 #201 ⬜ docker-all scripts

1. S131 #202 ⬜ docker-all-up.sh starts all local containers.
2. S132 #203 ⬜ docker-all-down.sh stops and removes them.
3. S133 #204 ⬜ docker-all-status.sh reports each container's state.

### E016 #183 ⬜ Local developer commands

#### F052 #205 ⬜ package.json container commands

1. S134 #206 ⬜ local:containers:all:start / stop / status map to docker-all scripts.
2. S135 #207 ⬜ Per-service container commands.

#### F053 #208 ⬜ uv for Python

1. S136 #209 ⬜ uv setup with lockfiles per service; Python version pinned.
2. S137 #210 ⬜ CI installs and tests with uv.

## M009: Entitlements API Service

Status: **Open — 21 open, 0 closed (21 total)**. Goal: FastAPI Entitlements service: signup, signin, obtain features, roles. Exit criteria: local signup → signin → GET /features works end to end; migrations apply on start; 6 roles seeded.

### E017 #184 ⬜ Entitlements API

#### F054 #211 ⬜ FastAPI service skeleton

1. S138 #212 ⬜ entitlements_api: FastAPI app + uv project + Dockerfile + health endpoint.
2. S139 #213 ⬜ Config via environment (DB URL, Redis URL, JWT secret).
3. S140 #214 ⬜ CI runs its tests.

#### F055 #215 ⬜ entitlements_db schema & migrations

1. S141 #216 ⬜ entitlements_db schema: users, roles, entitlements tables.
2. S142 #217 ⬜ Alembic migrations: versioned, up/down, applied on start.
3. S143 #218 ⬜ Seed data: the 6 roles.

#### F056 #219 ⬜ SignUp & SignIn

1. S144 #220 ⬜ POST /signup: validation, password hashing, default role.
2. S145 #221 ⬜ POST /signin: credential check, JWT access + refresh tokens.
3. S146 #222 ⬜ Token-verification dependency protecting endpoints.

#### F057 #223 ⬜ Obtain features

1. S147 #224 ⬜ GET /features returns the caller's entitlements.
2. S148 #225 ⬜ Role → feature mapping stored in tables.
3. S149 #226 ⬜ New roles can be added without code changes.

#### F058 #227 ⬜ bin/start-app.sh (migrate then start)

1. S150 #228 ⬜ start-app.sh runs migrations, then starts Uvicorn.
2. S151 #229 ⬜ Local run works via package.json local:middleware:apis:all:start.
3. S152 #230 ⬜ Health + logs visible (ELK, docker-all-status).

## M010: Microservice Images, Pattern & Portals

Status: **Open — 21 open, 0 closed (21 total)**. Goal: every microservice builds an image, follows one template, portals run locally. Exit criteria: Entitlements image in ECR via manual AWS-012; second service bootstraps from the template; Loan-Advisor runs locally against local APIs.

### E018 #185 ⬜ Microservice template & local runners

#### F059 #231 ⬜ Microservice template

1. S153 #232 ⬜ Template layout documented (bin/start-app.sh, uv, Dockerfile, health endpoint).
2. S154 #233 ⬜ A second service bootstraps from the template.

#### F060 #234 ⬜ package.json middleware & portals commands

1. S155 #235 ⬜ local:middleware:apis:all:start / stop / status run the .sh runners.
2. S156 #236 ⬜ local:portals:all:start / stop / status run the portal .sh runners.

#### F061 #237 ⬜ Portals local startup

1. S157 #238 ⬜ Loan-Advisor runs locally against the local APIs.
2. S158 #239 ⬜ Signup → signin flow works end to end from the portal.

### E019 #186 ⬜ Container images & ECR publishing

#### F062 #240 ⬜ CI builds images on main only

1. S159 #241 ⬜ ci.yaml builds microservice Docker images only on main branch.
2. S160 #242 ⬜ PR / branch runs skip image builds.

#### F063 #243 ⬜ AWS-012: build & publish Entitlements image to ECR

1. S161 #244 ⬜ Manual workflow builds the entitlements image.
2. S162 #245 ⬜ Image pushed to ECR repo <project>-entitlements.
3. S163 #246 ⬜ Manual trigger only; no auto-publish on push.

#### F064 #247 ⬜ Image pattern per microservice

1. S164 #248 ⬜ Reusable build workflow (or per-service convention) documented.
2. S165 #249 ⬜ The next microservice gets its image workflow by copying the pattern.

## The gates between milestones

These rules decide when you may move on. They are not visible in GitHub's
milestone view — they live here.

1. **M001 → M002 → M003 → M004 → M005.** Do not start M004 before M003 is
done — the cloud pipeline amplifies whatever the local generator does,
good or bad. Do not scale to 200k/year (M005) until the M003 uniqueness
numbers and the dedup audit (F021) are clean.
2. **M006 → M007.** Do not start M007 before M006 is done. M006 also
needs generated documents to exist — indexing cannot run on an empty
corpus.
3. **F033 before F032.** Delete the data before destroying the infra:
run AWS-009 (or AWS-Index-009) before AWS-010 (or AWS-Index-010).
CloudFormation cannot delete a non-empty S3 bucket, and the buckets
are versioned — emptying must delete every version and delete marker.
4. **Current state (2026-11-12):** all AWS infrastructure was torn down
and verified gone (AWS-099 ALL CLEAR). Nothing is deployed. Before any
M004/M006/M007 work can run again, rebuild first — see HANDOVER.md §3.
The VPC question (default VPC vs create-new) is still open and blocks
any rebuild.
5. **M008 → M009 → M010.** Do not start M009 before M008 is done — the Entitlements service needs local Postgres/Redis running. Do not start M010 before M009 — the microservice template and the AWS-012 image workflow are copied from the Entitlements service.
