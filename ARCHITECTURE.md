# ARCHITECTURE — RAG Corpus (Banking Loans)

> Companion to `README.md` (how to use it) and `DESIGN.md` (why it is
> designed this way). This document describes the system as built:
> components, data flow, scaling, failure handling, security, and cost.
> If code and this document disagree, the code is wrong — fix the code,
> or update this document in the same change.

---

## Table of contents

1. [Goals and constraints](#1-goals-and-constraints)
2. [System overview](#2-system-overview)
3. [Components](#3-components)
4. [Data flow — one run, step by step](#4-data-flow--one-run-step-by-step)
5. [Sharding and parallelism](#5-sharding-and-parallelism)
6. [Storage layout](#6-storage-layout)
7. [Retry, idempotency, and failure modes](#7-retry-idempotency-and-failure-modes)
8. [Security](#8-security)
9. [Observability](#9-observability)
10. [Scaling and cost](#10-scaling-and-cost)
11. [What Lambda is — and is not — for here](#11-what-lambda-is--and-is-not--for-here)
12. [Alternatives considered](#12-alternatives-considered)
13. [Deployment topology](#13-deployment-topology)
14. [Limitations and known gaps](#14-limitations-and-known-gaps)

---

## 1. Goals and constraints

**Goals:**

1. Generate 200,000 loan records per annum, last 10 years, per
   document type — 2M records per format, 12M files total.
2. Each record rendered in six formats (PDF, DOCX, XLSX, CSV, TXT,
   PNG) with identical facts, so RAG retrieval can be compared across
   parsers.
3. Descriptions must be *unique enough* for RAG to work (see
   `README.md §5`): wording-only overlap must stay low, or retrieval
   is meaningless.
4. Runs must be resumable and safe to retry: a failure must never
   create duplicates or lose a shard.
5. Professional operation: code in GitHub, infra as code, manual
   triggers per format, no secrets in the repo, observable failures.

**Constraints:**

- No real customer data. All content is synthetic / fictional.
- No AWS account is connected to this repo yet. Infra is defined
  and validated, not deployed.
- Batch workers run in a customer VPC (subnets / security groups
  supplied via GitHub Secrets), not in a public default VPC.
- The generator must run locally with no AWS dependencies, so it can
  be tested and measured before any cloud spend.

**Non-goals (explicitly out of scope):**

- RAG ingestion: chunking, embedding, vector storage, retrieval.
  The corpus is the *input* to that later stage.
- A policy corpus. See `DESIGN.md §3`.
- Real-time generation. All generation is batch, triggered manually.

---

## 2. System overview

```
                        GitHub
                          │
            ┌─────────────┼─────────────┐
            │             │             │
   aws-001-provision-infra   generate-<fmt>   ci
   (manual)          (manual, ×6)    (push/PR)
            │             │
            ▼             ▼
   CloudFormation    Step Functions
   stacks            (Plan → Submit)
            │             │
            ▼             ▼
   S3 / DynamoDB   Planner Lambda ──► SQS FIFO ──► AWS Batch
   SQS / ECR /        (shards)          (shards)    (Fargate Spot)
   Batch / Lambda                                  │
                                                   ▼
                                            S3 + DynamoDB
                                            (corpus + manifest)
```

**Control plane vs data plane — the central split:**

| Plane | Services | Characteristics |
|---|---|---|
| Control plane | GitHub Actions, CloudFormation, Step Functions, Planner Lambda, SQS | Short-lived, stateless, cheap, orchestrates work |
| Data plane | AWS Batch (Fargate Spot), S3, DynamoDB | Long-running, heavy, parallel, does the work |

Lambda never generates documents at scale. Batch never decides what
to generate. That separation is what makes the system retryable and
scalable — see §11.

---

## 3. Components

### 3.1 GitHub + GitHub Actions

- **Source of truth** for code, infra, and workflows.
- **CI (`ci.yml`):** tests + py_compile on push/PR. No AWS access.
- **Provision (`aws-001-provision-infra.yml`):** manual `workflow_dispatch`.
  Deploys CloudFormation stacks in order. Uses AWS credentials and
  VPC details from GitHub Secrets (§8 in README).
- **Generate (per format):** six manual `workflow_dispatch` workflows,
  `aws-003-generate-pdf.yml` … `aws-008-generate-png.yml`. Thin wrappers — each only
  names its format and passes `count`, `year`, `shard_size`, `seed`.
- **Generate (shared):** `aws-002-generate.yml`, a reusable `workflow_call`
  workflow. Starts the Step Functions execution for one format + year.

### 3.2 CloudFormation — infra as code

Three stacks, deployed in order. Terraform was the earlier version;
it is archived under `infra/archive-terraform/` and is **not** used.

| Stack | Template | Resources |
|---|---|---|
| `<project>-storage` | `Middleware/Workflows/Datagen/infra/cloudformation/storage.yaml` | S3 corpus bucket (versioning, AES-256, Intelligent-Tiering after 30d), DynamoDB manifest table, DynamoDB dedup table, SQS FIFO queue + DLQ |
| `<project>-compute` | `Middleware/Workflows/Datagen/infra/cloudformation/compute.yaml` | ECR repository, Batch service role, Batch task + execution roles, Batch Fargate Spot compute environment, job queue, job definition |
| `<project>-orchestration` | `Middleware/Workflows/Datagen/infra/cloudformation/orchestration.yaml` | Planner Lambda + role, Step Functions state machine + role, DLQ CloudWatch alarm |

Stacks communicate via CloudFormation **exports/imports**
(`Fn::ImportValue`): the compute stack imports the SQS queue URL
from storage; orchestration imports the job queue / definition ARNs
from compute.

Parameters that come from GitHub Secrets (never hard-coded):
`VpcId`, `SubnetIds`, `SecurityGroupIds`, `MaxVcpus`, `Project`.

### 3.3 Step Functions

State machine (`Middleware/Workflows/Datagen/infra/stepfunctions/state-machine.json`, mirrored in
`orchestration.yaml`):

```
PlanShards (Lambda:invoke, retry 3×, backoff)
  → SubmitBatchWorkers (batch:submitJob.sync, retry 3×, backoff)
  → Succeed
```

`submitJob.sync` waits for the Batch job to finish, so the state
machine represents one whole format+year run. Input and output
schemas are in `DESIGN.md §7`.

### 3.4 Planner Lambda

- Runtime: Python 3.12, timeout 120s, code packaged as `planner.zip`
  by the provision workflow and stored in S3.
- Input: `{total_per_format, shard_size, formats: ["pdf"], year,
  seed, run_id}`.
- Output: `{run_id, formats, year, shards_enqueued, shards: [...]}`.
- Behaviour: computes `ceil(total / shard_size)` shards, sends one
  SQS message per shard in batches of 10, with
  `MessageDeduplicationId = run_id + shard_id` and
  `MessageGroupId = run_id`.
- Permissions (least privilege): `sqs:SendMessageBatch` on the
  shards queue only, plus CloudWatch Logs.

### 3.5 SQS FIFO queue + DLQ

- Queue: `<project>-shards.fifo`, FIFO, content-based deduplication,
  visibility timeout 3600s, retention 14 days.
- DLQ: `<project>-shards-dlq.fifo`, same settings.
- Redrive policy: `maxReceiveCount = 3`. After 3 failed receives,
  a shard message moves to the DLQ. Nothing is lost.
- Replay: `scripts/enqueue_shards.py --dlq-url … --queue-url …`
  moves DLQ messages back to the main queue.

Why FIFO: deduplication IDs and per-run message grouping. A standard
queue would allow the same shard to be enqueued twice in a short
window; FIFO + dedup ID prevents that. FIFO does not prevent
duplicates over longer windows — the S3 `.done` marker does (§7).

### 3.6 AWS Batch — Fargate Spot

- Compute environment: `FARGATE_SPOT`, max vCPUs configurable
  (default 64), subnets + security groups from GitHub Secrets.
- Job queue: `<project>-queue`, priority 1.
- Job definition: `<project>-worker`, container image from ECR
  (`:latest`), 2 vCPU / 4096 MB, retry strategy 3 attempts,
  environment: `CORPUS_BUCKET`, `MANIFEST_TABLE`, `QUEUE_URL`,
  `AWS_REGION`.
- Task role (least privilege): S3 Put/Get/Head on the corpus bucket,
  DynamoDB PutItem on manifest + dedup tables, SQS Receive/Delete
  on the shards queue, CloudWatch Logs.
- Execution role: standard `AmazonECSTaskExecutionRolePolicy`.

Workers poll SQS with long polling (20s), one message at a time,
visibility timeout 3600s. A worker exits when one idle poll returns
no messages — the Batch job then completes and Step Functions
(`submitJob.sync`) returns.

### 3.7 S3

- Bucket: `<project>-corpus-<account-id>`, versioning enabled,
  AES-256 encryption, lifecycle to Intelligent-Tiering after 30 days.
- Layout: see §6.
- The bucket is also the Lambda code store for `planner.zip`
  (`lambda/planner.zip`).

### 3.8 DynamoDB

Two tables, both `PAY_PER_REQUEST` (no capacity provisioning):

| Table | PK | Purpose |
|---|---|---|
| `<project>-manifest` | `doc_id` (`<format>_<idx>`) | Ground-truth manifest. GSI on `loan_id`. One row per generated file. |
| `<project>-dedup` | `natural_hash` | Duplicate claim table. PK is the hash of the unique description fields. See `DESIGN.md §6`. |

### 3.9 ECR

Repository `<project>-worker`, scan-on-push enabled. The provision
workflow builds the worker image from `Middleware/Workflows/Datagen/Dockerfile` and pushes
`:latest` (and the commit SHA tag in CI, if enabled). The Batch job
definition references `:latest`.

### 3.10 CloudWatch

- Logs: `/aws/batch/job` (Batch workers), `/aws/lambda/<project>-planner`.
- Alarm: `<project>-dlq-depth` — fires when
  `ApproximateNumberOfMessagesVisible` on the DLQ > 0 for one 5-minute
  period. That is the signal that shards are failing.

---

## 4. Data flow — one run, step by step

Example: generate PDFs for 2024, 200,000 records.

1. **Operator** runs Actions → AWS-003 Generate PDF, inputs
   `count=200000, year=2024, shard_size=10000, seed=7`.
2. **Reusable workflow** (`aws-002-generate.yml`) starts Step Functions with
   `run_id = "2024-pdf-<timestamp>"` and the input above.
3. **Planner Lambda** computes 20 shards (`start=0,10000,…,190000`),
   sends 20 SQS messages.
4. **Step Functions** submits one Batch job
   (`submitJob.sync`) and waits.
5. **Batch workers** (Fargate Spot, in parallel) poll SQS. Each
   worker takes one shard message.
6. For each record in the shard (10,000 records):
   - Generate the record deterministically (`seed + start + year`).
   - Compute wording shingles; if overlap vs kept descriptions
     exceeds 0.65, regenerate with a different variant/layout
     (up to 5 attempts).
   - Render the record in PDF (the run's only format).
   - Upload to S3 at
     `raw/pdf/year=2024/month=MM/day=DD/loan_<idx>_<loan_id>.pdf`.
   - Upsert the DynamoDB manifest row; claim the dedup hash.
7. Worker writes the shard manifest
   (`manifests/<run_id>/<shard_id>.jsonl`) and the `.done` marker
   (`markers/<run_id>/<shard_id>.done`) to S3.
8. Worker deletes the SQS message — only now, on full success.
9. When the queue is empty, workers exit, the Batch job completes,
   Step Functions returns success.
10. **Operator** verifies: S3 object count for `raw/pdf/year=2024/`
    and DynamoDB `COUNT` for that `run_id` should both be 200,000.

---

## 5. Sharding and parallelism

- **Shard = a record range**, not a format. One shard = 10,000
  records × the run's format(s). A per-format-per-year run (200k)
  is 20 shards. All 10 years × 6 formats is 60 runs × 20 shards =
  1,200 shards total, each independent.
- **Determinism:** shard `n` always covers records
  `[n×shard_size, (n+1)×shard_size)` for its seed + year. Re-running
  the same shard reproduces the same files.
- **Parallelism:** Batch scales out by available vCPUs (max 64 by
  default). Shards are independent — there is no cross-shard
  coordination except the DynamoDB dedup claim, which is atomic.
- **Why 10,000?** Large enough to amortise worker startup and SQS
  polling, small enough that a failed shard is cheap to retry and
  fits in the 1-hour SQS visibility timeout. Change it via the
  workflow `shard_size` input; update the Planner and the worker's
  visibility timeout together if you raise it a lot.
- **Resume:** a re-run of the same format+year skips shards with a
  `.done` marker and overwrites identical files for the rest.

---

## 6. Storage layout

### S3

```
s3://<bucket>/
  raw/<format>/year=YYYY/month=MM/day=DD/loan_<idx>_<loan_id>.<ext>
  manifests/<run_id>/<shard_id>.jsonl
  markers/<run_id>/<shard_id>.done
  lambda/planner.zip
```

- Partition is by **loan start date** (event date), not generation
  date. This is what makes "all PDFs for 2024" a prefix scan, and
  what Athena/Glue understand as Hive-style partitions.
- One file per record per format. No bundling — RAG ingestion tests
  need individual documents, not archives.
- Manifests and markers are per run + shard, so a run can be audited
  and resumed shard by shard.

### DynamoDB manifest — item shape

```json
{
  "doc_id": "pdf_0000000",
  "format": "pdf",
  "s3_key": "raw/pdf/year=2024/month=03/day=12/loan_0000000_711097000000.pdf",
  "loan_id": "711097000000",
  "loan_type": "Business Loan",
  "channel": "partners",
  "question": "What is the interest rate for a business loan?",
  "answer": "The interest rate for a Business Loan is 11.37% …",
  "run_id": "2024-pdf-20261112-083000",
  "shard_id": "shard-0000",
  "year": 2024, "month": 3, "day": 12
}
```

Full schemas: `DESIGN.md §7`.

---

## 7. Retry, idempotency, and failure modes

**Retry layers (in order):**

| Layer | Mechanism | Limit |
|---|---|---|
| Step Functions | Task retry, exponential backoff | 3 attempts |
| AWS Batch | Job retry strategy | 3 attempts |
| SQS | Visibility timeout + redelivery | 3 receives, then DLQ |
| DLQ | Manual replay via `Middleware/Workflows/Datagen/scripts/enqueue_shards.py` | 14-day retention |

**Idempotency guards:**

1. Deterministic generation: same seed + start + year = same records.
2. Deterministic S3 keys: same record = same key, same content on overwrite.
3. DynamoDB manifest upsert: same `doc_id` + same values on retry.
4. Dedup hash claim: atomic `attribute_not_exists` on the dedup table.
5. Shard `.done` marker: replay skips finished shards.

**Failure modes:**

| Failure | What happens | Recovery |
|---|---|---|
| Batch worker crashes mid-shard | SQS message becomes visible again after 1h; another worker retries the shard | Automatic; `.done` marker prevents double work on the parts already done only if the marker was written — otherwise the shard is regenerated identically |
| Planner Lambda fails | Step Functions retries; no shards are enqueued twice, because SQS dedup ID is `run_id + shard_id` | Automatic |
| S3 throttling | `boto3` adaptive retry (5 attempts) in the worker | Automatic; if it persists, reduce Batch vCPUs |
| DynamoDB throttling | Same adaptive retry; `PAY_PER_REQUEST` scales, but hot partitions on one `doc_id` prefix are unlikely | Automatic |
| Spot interruption | Batch retries the job (3 attempts) on another Spot host | Automatic; use on-demand Fargate if Spot interruptions become frequent |
| DLQ non-empty | Alarm fires; shards need inspection | Read Batch logs, fix the cause, replay the DLQ — do not re-run the whole year |
| Bad generator code | Shards fail fast; DLQ fills | Fix the code, push, re-provision the image, replay only the failed shards |

---

## 8. Security

- **Credentials:** GitHub Actions uses long-lived AWS access keys
  stored as GitHub Secrets (`AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`). This is the design the repo owner chose.
  A stronger option is OIDC (no stored keys) — see `DESIGN.md §10`
  for the trade-off and how to switch.
- **Secrets in repo:** none. VPC ID, subnet IDs, security group IDs,
  account ID, and region are all GitHub Secrets or CloudFormation
  parameters. The example parameter file
  (`prod.json.example`) contains placeholders only.
- **IAM — least privilege:** each role can only do its job. The
  Batch task role can write to the corpus bucket and the two
  DynamoDB tables, and read/delete from the shards queue — nothing
  else. The Planner role can only send to the shards queue. The
  Step Functions role can only invoke the Planner and submit Batch
  jobs.
- **Network:** Batch Fargate tasks run in the customer VPC, in
  private subnets supplied via secrets. They need outbound access
  to S3/DynamoDB/SQS — via a NAT gateway or VPC endpoints. There is
  no public IP on the tasks.
- **Data:** S3 is AES-256 encrypted at rest, versioning enabled.
  DynamoDB is encrypted at rest by default. All generated data is
  synthetic/fictional — no real PII is in the corpus by design.
- **ECR:** image scanning on push.

---

## 9. Observability

- **Logs:** Batch worker logs → CloudWatch Logs `/aws/batch/job`.
  Planner logs → `/aws/lambda/<project>-planner`. Step Functions
  execution history shows each state transition.
- **Metrics to watch:** SQS `ApproximateNumberOfMessagesVisible`
  (queue depth — should drain to 0), DLQ depth (should stay 0),
  Batch job success/failure counts, DynamoDB throttled requests,
  S3 object count per `raw/<format>/year=YYYY/` prefix.
- **Alarm:** DLQ depth > 0 (see §3.10). Add alarms for Batch
  failures and Step Functions failures before the first 200k run.
- **Audit:** the DynamoDB manifest is the audit log. Count rows by
  `run_id` to verify a run; scan the shard manifests in S3 to see
  exactly which files a shard wrote.

---

## 10. Scaling and cost

**Scale (full target):**

- 200,000 records/year × 10 years = 2,000,000 records per format
- × 6 formats = 12,000,000 files
- 1,200 shards of 10,000 records (200 per format)

**Cost drivers, in order:**

1. **Batch Fargate Spot compute** — dominates. Depends on vCPUs,
   memory, and how long a shard takes. Measure one 10k shard first,
   then multiply. Spot is typically 60–70% cheaper than on-demand
   Fargate; if Spot interruptions rise, switch the compute
   environment type to `FARGATE`.
2. **S3 storage** — 12M files, tens of GB (PDFs and PNGs dominate).
   Intelligent-Tiering after 30 days helps. Versioning doubles
   storage if files are overwritten often — overwrites here are
   identical, so versioning cost stays low in practice.
3. **DynamoDB** — 12M manifest writes + 2M dedup claims, on-demand.
   Small compared with compute.
4. **SQS / Lambda / Step Functions** — negligible at this scale.

**Cost controls built in:**

- Manual triggers only. Nothing runs on a schedule and nothing
  auto-scales to 12M files by accident.
- Start with 1,000 records per format per year. Measure time, cost,
  and S3 size, then scale.
- One format + one year at a time. Do not start all 60 runs at once.

---

## 11. What Lambda is — and is not — for here

This is an ETL-style pipeline (generate → transform → load to S3 /
DynamoDB), but Lambda is only right for part of it:

- **Lambda is right for:** the Planner (seconds, stateless),
  small event-driven transforms (one file in → parse → write),
  validation, DLQ replay, and glue code.
- **Lambda is wrong for:** bulk generation. A 10k-record shard runs
  far longer than Lambda's 15-minute limit, needs more memory/disk,
  and at 12M files would mean millions of invocations.

That is why the architecture splits control plane (Lambda) from data
plane (Batch). The later RAG *ingestion* stage — S3 file lands →
parse → chunk → embed → load — is the stage where Lambda is the
right tool. It is out of scope for this repo.

AWS Glue is the other ETL option: best for Spark-scale tabular ETL
with a Data Catalog. It is awkward for generating PDFs/DOCX/PNGs
with custom Python, which is why Batch was chosen here.

---

## 12. Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Terraform instead of CloudFormation | The repo owner chose CloudFormation + GitHub Actions for provisioning. Terraform is archived for reference. Functionally equivalent; CloudFormation is AWS-native and needs no separate state backend. |
| Lambda-only generation | 15-minute limit, 10 GB memory, millions of invocations. Not viable for 10k-record shards. |
| AWS Glue (Spark) | Great for tabular ETL, poor for binary formats (PDF/DOCX/PNG) and custom Pillow rendering. |
| EMR / ECS on EC2 | More control, more operational burden. Fargate Spot gives the same parallelism without managing instances. |
| Single monolithic run (no shards) | One failure loses everything; no parallelism; no resume. Sharding is what makes 12M files tractable. |
| S3 without date partitions | Works, but "all of 2024" becomes a full-bucket scan. The `year=/month=/day=` partition makes per-year runs, queries, and lifecycle rules cheap. |

---

## 13. Deployment topology

```
GitHub (repo + Actions)
  │
  │  aws-001-provision-infra.yml (manual)
  ▼
AWS account (region from secrets, e.g. ap-south-1)
  │
  ├── CloudFormation stacks: <project>-storage / -compute / -orchestration
  ├── S3: <project>-corpus-<account-id>
  ├── DynamoDB: <project>-manifest, <project>-dedup
  ├── SQS: <project>-shards.fifo, <project>-shards-dlq.fifo
  ├── ECR: <project>-worker
  ├── Batch: Fargate Spot compute env in customer VPC (private subnets)
  ├── Lambda: <project>-planner
  ├── Step Functions: <project>-run
  └── CloudWatch: logs + DLQ alarm
```

One AWS account, one region, one project prefix. Multi-region or
multi-account deployment is not in scope — add it by parameterising
`Project` and `AWS_REGION` per environment, and by using a separate
GitHub environment per account.

---

## 14. Limitations and known gaps

1. **No deployment has happened yet.** Templates are validated
   (YAML/JSON/Python), not applied. The first `aws-001-provision-infra` run
   is the real test.
2. **Uniqueness check is pairwise** in `Middleware/Workflows/Datagen/uniqueness_check.py` (O(n²)).
   It is fine at 200 records, not at 1M. At scale, use MinHash/LSH
   in the Batch worker — the dedup table is the hook for that.
3. **PNG text rendering** uses Pillow's default bitmap font. It is
   legible for testing OCR, not production-quality typography.
4. **No cost measurement yet.** Measure one 10k shard before
   committing to 200k/year.
5. **Secrets are long-lived keys**, not OIDC. See `DESIGN.md §10`
   for how to switch.
6. **No multi-format run in one workflow.** Each format is a
   separate manual run by design. A combined run would be a new
   workflow that calls `aws-002-generate.yml` six times.
