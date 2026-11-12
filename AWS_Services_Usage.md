# AWS Services — Usage Guide

What each AWS service does in this project, the exact resource names, and
when each part runs. Everything here is provisioned by AWS-001 (Datagen)
and AWS-Index-001 (DataIndexing) from the CloudFormation templates under
`Middleware/Workflows/*/infra/cloudformation/`. Nothing in this file is
theory — it describes the stacks that are actually deployed in us-east-1.

## Table of contents

- [1. Overview — the services at a glance](#1-overview--the-services-at-a-glance)
- [2. AWS Step Functions](#2-aws-step-functions)
- [3. AWS Batch](#3-aws-batch)
- [4. Amazon S3](#4-amazon-s3)
- [5. Amazon SQS](#5-amazon-sqs)
- [6. AWS Lambda](#6-aws-lambda)
- [7. Amazon RDS (PostgreSQL + pgvector)](#7-amazon-rds-postgresql--pgvector)
- [8. Amazon DynamoDB](#8-amazon-dynamodb)
- [9. Amazon ECR](#9-amazon-ecr)
- [10. Amazon Bedrock](#10-amazon-bedrock)
- [11. AWS CloudFormation](#11-aws-cloudformation)
- [12. Amazon CloudWatch](#12-amazon-cloudwatch)
- [13. Amazon EventBridge](#13-amazon-eventbridge)
- [14. AWS Secrets Manager](#14-aws-secrets-manager)
- [15. AWS IAM](#15-aws-iam)
- [16. Amazon VPC & networking](#16-amazon-vpc--networking)
- [17. Amazon CloudTrail](#17-amazon-cloudtrail)
- [18. Checking status & troubleshooting](#18-checking-status--troubleshooting)
- [19. Costs (approximate)](#19-costs-approximate)

## 1. Overview — the services at a glance

| Service | Used for | Key resources |
|---|---|---|
| Step Functions | Orchestrating a generate run and an index run | `rag-corpus-run`, `rag-corpus-index-run` |
| Batch | The heavy work: generating documents, indexing them | `rag-corpus-worker`, `rag-corpus-indexer` |
| S3 | All documents, manifests, done markers | `rag-corpus-corpus-787193426426` |
| SQS | Shard queues between the planner and the workers | `rag-corpus-shards.fifo`, `rag-corpus-index-shards.fifo` |
| Lambda | Planning a run into shards | `rag-corpus-planner`, `rag-corpus-index-planner` |
| RDS (PostgreSQL) | The vector index (pgvector) | `rag-corpus-index-db` |
| DynamoDB | Manifests and dedup records | `rag-corpus-manifest`, `rag-corpus-dedup`, `rag-corpus-index-manifest` |
| ECR | Worker container images | `rag-corpus-worker`, `rag-corpus-indexer` |
| Bedrock | Embeddings for indexing | `amazon.titan-embed-text-v2:0` (default) |
| CloudFormation | All infrastructure as code | 6 stacks (see §11) |
| CloudWatch | Batch job logs, RDS logs, alarms | Log group `/aws/batch/job` |
| EventBridge | Managed rules that watch Batch jobs for Step Functions | Created automatically |
| Secrets Manager | The database password | `rag-corpus-index-db` |
| IAM | Roles for Lambda, Batch and Step Functions | Per-stack roles (see §15) |
| VPC | Private networking for Batch and RDS | `vpc-004fcdad2eea59207` |
| CloudTrail | Audit trail of AWS API calls | Trail + trail bucket |

`<PROJECT>` is `rag-corpus` and the account is `787193426426`
(region `us-east-1`) unless a name says otherwise.

## 2. AWS Step Functions

Step Functions is AWS's way of running a job in steps, in order, and
knowing whether it finished. Think of it as a recipe: step 1 runs, then
step 2 runs, and Step Functions keeps track of where the run is.

In this project there are two such recipes, called *state machines*.
One makes the documents, the other indexes them. Each machine has
exactly two steps. Both were created by the provision workflows
(AWS-001 and AWS-Index-001) and both are **Active** — meaning they are
ready to run. You do not need to touch the console to run them: you
start them from GitHub Actions, and you check them with AWS-011
(see §18).

### 2.1 `rag-corpus-run` — make the documents (Datagen)

**Purpose.** Create a batch of synthetic loan documents (PDF, DOCX,
XLSX, CSV, TXT or PNG) and store them in S3, so the RAG system has
something to answer questions from.

**What it does, step by step.**

1. `CustomerCase-PlanShards` — plan the work. A small Lambda function
   (`rag-corpus-planner`) splits the requested amount into batches of
   10,000 records and puts one message per batch onto a queue. For
   example, 100 documents = 1 batch; 200,000 documents = 20 batches.
   If this step fails it tries again, up to 3 times.
2. `CustomerCase-SubmitBatchWorkers` — do the work. Step Functions
   starts one Batch job (`rag-corpus-worker`) that takes the batches off
   the queue one by one and writes the documents into S3. The job runs
   on Fargate Spot (cheap, short-lived compute). The step *waits* for
   the job to finish before the machine ends — that is what `.sync`
   means. If this step fails it tries again, up to 3 times, each time
   starting a fresh Batch job.

**How it is set up in Step Functions.** It is a *Standard* state
machine (the normal type — it keeps a full history of every step and
lets you see what happened). It lives in the orchestration stack
`rag-corpus-orchestration`. Its full name is `rag-corpus-run`. The two
steps above are the whole machine — there is nothing else in it.

**How it starts.** From GitHub Actions, not from the console. Run one
of the wrappers — AWS-003 (PDF), AWS-004 (DOCX), AWS-005 (XLSX),
AWS-006 (CSV), AWS-007 (TXT) or AWS-008 (PNG) — and fill in `count`
(how many documents), `year`, `shard_size` (default 10000) and `seed`
(default 7). The workflow starts an *execution* (one run of the
machine), named `<year>-<format>-<date>-<time>`, e.g.
`2024-pdf-20261112-194138`.

**How often does it run?** Only when you start it. There is no
schedule and nothing runs automatically. Run it whenever you need
documents: a new format, a new year, or a test batch.

**Can it run multiple times?** Yes — as many times as you like. Every
execution gets a unique name (the date and time are part of it), so
runs never collide. Re-running the same format and year is also safe:
each batch is marked with a done-marker in S3, and a batch that is
already done is skipped instead of being generated again.

**What if it fails?** See §2.3 below.

### 2.2 `rag-corpus-index-run` — index the documents (DataIndexing)

**Purpose.** Make the documents searchable: read the loan documents
that are already in S3, split them into chunks, add metadata, turn
each chunk into a vector with Bedrock, and store the vectors in the
PostgreSQL database (pgvector) so the RAG system can find the right
chunks when someone asks a question.

**What it does, step by step.**

1. `CustomerCase-PlanShards` — plan the work. A Lambda function
   (`rag-corpus-index-planner`) lists the documents already in S3
   under `raw/<format>/year=<year>/`, splits them into batches of 100
   documents, and puts one message per batch onto a queue. If this
   step fails it tries again, up to 3 times.
2. `CustomerCase-SubmitBatchWorkers` — do the work. Step Functions
   starts one Batch job (`rag-corpus-indexer`) that takes the batches
   off the queue and, for each document, loads it, chunks it, adds
   metadata, embeds it with Bedrock and stores it in pgvector (and in
   OpenSearch, if that is switched on). Like the other machine, the
   step waits for the job to finish, and retries up to 3 times.

**How it is set up in Step Functions.** A Standard state machine,
created by the orchestration stack `rag-corpus-index-orchestration`.
Its full name is `rag-corpus-index-run`. Same two-step shape as the
generator — plan, then run one Batch job.

**How it starts.** From GitHub Actions: AWS-Index-003 (PDF) through
AWS-Index-008 (PNG). Fill in `count` (only used as a hint),
`year`, `shard_size` (default 100), `seed` and `embedding_model`
(a dropdown — pick a model, or leave `default`). The execution is
named `<year>-<format>-index-<date>-<time>`, e.g.
`2024-pdf-index-20261112-195007`.

**How often does it run?** Only when you start it. There is no
schedule. Run it **after** the documents for that format and year
exist in S3 — it indexes what is already there; it never creates
documents.

**Can it run multiple times?** Yes. Every execution has a unique
name. Running it again over the same documents is safe: chunks are
identified by their document, position and model, so re-indexing
writes the same chunks again instead of duplicating them. Re-run it
when you want to index with a different embedding model (that creates
a separate vector table per model) or to pick up new documents.

**What if it fails?** See §2.3 below.

### 2.3 What happens when a step fails

Retries stack up: a step retries up to 3 times, and every retry starts
a **new** Batch job, which itself tries up to 3 times. So one bad step
can run up to 9 containers before the execution finally turns
**Failed**. While the retries are still going, the execution shows
**Running** — that does not mean the work is progressing, only that
Step Functions has not given up yet. A one-off glitch fixes itself
this way; a real bug (a code error, a missing permission) just fails
nine times in a row. So do not wait the retries out — read the Batch
job's CloudWatch log to see the actual error. And remember: a green
tick on the GitHub Actions run only means the execution *started*.
To know whether it finished, run AWS-011 (see §18).

## 3. AWS Batch

The bulk work runs here, not in Lambda (Lambda's 15-minute limit is too
short for thousands of files). Both pipelines use Fargate Spot compute
environments.

| Item | Datagen | DataIndexing |
|---|---|---|
| Job queue | `rag-corpus-queue` | `rag-corpus-index-queue` |
| Job definition | `rag-corpus-worker` | `rag-corpus-indexer` |
| Job name | `rag-corpus-worker` | `rag-corpus-indexer` |
| Image | `rag-corpus-worker:latest` | `rag-corpus-indexer:latest` |
| Size | 2 vCPU / 4096 MB | 2 vCPU / 4096 MB |
| Container retries | 3 attempts | 3 attempts |

- The **worker** polls its SQS queue one message at a time, generates the
  shard's documents into S3, writes the manifest and a `.done` marker,
  then deletes the message. An empty queue ends the job with exit 0 —
  so a job can succeed while having processed nothing (a failed shard
  leaves its message invisible for an hour instead of deleting it).
- The **indexer** polls its queue the same way, and for each document
  loads it, chunks it, enriches it with metadata, embeds it with
  Bedrock and stores it in pgvector. It connects to the database before
  polling, so a database failure kills the job at startup.
- Logs go to CloudWatch log group `/aws/batch/job`, stream
  `<job-name>/default/<task-id>`.

## 4. Amazon S3

One corpus bucket: **`rag-corpus-corpus-787193426426`**.

| Path | What lives there |
|---|---|
| `raw/<format>/year=<year>/month=<month>/day=<day>/loan_<idx>_<loan_id>.<ext>` | The generated documents (Hive-style partitions) |
| `manifests/<run_id>/<shard_id>.jsonl` | Ground-truth manifest for one shard (one line per document) |
| `markers/<run_id>/<shard_id>.done` | Per-shard done marker (Datagen) |
| `index-markers/<run_id>/<shard_id>.done` | Per-shard done marker (DataIndexing) |

A second bucket (in the storage stack) holds the CloudTrail trail logs.
The worker roles need `s3:GetObject`, `s3:PutObject` and `s3:HeadObject`
on the bucket's objects — and `s3:ListBucket` on the bucket itself,
because without it S3 answers a `HeadObject` on a missing key with 403
instead of 404, which breaks the worker's already-done marker check.

## 5. Amazon SQS

Two FIFO queues, one per pipeline, each with a dead-letter queue
(`maxReceiveCount` 3 — a message that fails 3 times goes to the DLQ).

| Queue | Used by |
|---|---|
| `rag-corpus-shards.fifo` | Datagen: planner → worker |
| `rag-corpus-index-shards.fifo` | DataIndexing: planner → indexer |

Message group ID is the run ID, and the deduplication ID is
`<run_id>-<shard_id>`, so re-planning the same run is idempotent — the
same shard is never enqueued twice.

## 6. AWS Lambda

Two planner functions, nothing else runs on Lambda.

| Function | What it does |
|---|---|
| `rag-corpus-planner` | Computes shards from `total_per_format` / `shard_size` (ceil division) and enqueues them. Invoked by `CustomerCase-PlanShards` in `rag-corpus-run`. |
| `rag-corpus-index-planner` | Lists S3 keys for the format + year, plans 100-document shards and enqueues them. Invoked by `CustomerCase-PlanShards` in `rag-corpus-index-run`. |

Both only plan and enqueue; they do no document work. (Note: Lambda
reserves the `AWS_REGION` environment variable — the templates do not
set it; the functions read the runtime value instead.)

## 7. Amazon RDS (PostgreSQL + pgvector)

| Item | Value |
|---|---|
| Instance | `rag-corpus-index-db` |
| Engine | PostgreSQL 18.3 (RDS default in us-east-1 once the 15.8 pin was removed) |
| Class | `db.t4g.micro`, MultiAZ `false` |
| Database / user | `ragindex` / `ragindex` |
| Access | Private only (not publicly accessible); lives in the VPC's DB subnet group |
| Secret | `rag-corpus-index-db` in Secrets Manager (password) |

The indexer stores the vector index here: `documents`, `chunks`, and
one `chunk_embeddings_<model slug>` table per embedding model, with an
HNSW index (`vector_cosine_ops`). The `vector` extension is created by
the indexer on first connect. The database's PostgreSQL log is in
CloudWatch under the RDS log files (`error/postgresql.log.YYYY-MM-DD-HH`
— the plain `error/postgres.log` is only a 200-byte redirect stub).

## 8. Amazon DynamoDB

| Table | Key | Used for |
|---|---|---|
| `rag-corpus-manifest` | `doc_id` (PK), GSI on `loan_id` | Ground-truth manifest of generated documents |
| `rag-corpus-dedup` | — | Deduplication records |
| `rag-corpus-index-manifest` | `chunk_id` (PK), GSI on `doc_id` | Which chunks were indexed, by which model |

## 9. Amazon ECR

Two repositories, one image each (tag `:latest`):

| Repository | Image |
|---|---|
| `rag-corpus-worker` | Datagen worker (generator + Batch worker) |
| `rag-corpus-indexer` | Indexing worker |

The provision workflows build and push the images after the compute
stacks create the repositories (the order matters — pushing before the
repository exists fails).

## 10. Amazon Bedrock

Embeddings only — no text generation in this project.

- Default model: **`amazon.titan-embed-text-v2:0`** (1024 dimensions).
- The Actions run UI offers a dropdown
  (`default`, `amazon.titan-embed-text-v2:0`,
  `amazon.titan-embed-text-v1:0`, `cohere.embed-english-v3`,
  `cohere.embed-multilingual-v3`); `default` means "use the configured
  default". Per-format overrides live in
  `config/embedding_models.yaml` (all `null` = use default).
- No manual enablement step: serverless foundation models (including
  Titan) are automatically enabled on first invoke in a commercial
  region. The indexer task role needs `bedrock:InvokeModel`.
- On a model error (access denied / not found / validation), the
  indexer fails over once to the default model and re-enriches the
  chunk with the model actually used.

## 11. AWS CloudFormation

All infrastructure is CloudFormation (under
`Middleware/Workflows/*/infra/cloudformation/`), deployed by AWS-001
and AWS-Index-001. Six stacks:

| Stack | Contents |
|---|---|
| `rag-corpus-vpc` | VPC, subnets, NAT gateway, security groups |
| `rag-corpus-storage` | Corpus bucket, manifest/dedup tables, SQS queues, CloudTrail |
| `rag-corpus-compute` | ECR repo, Batch compute env, job queue + definition, worker image |
| `rag-corpus-orchestration` | Planner Lambda, `rag-corpus-run` state machine, DLQ alarm |
| `rag-corpus-indexing` | RDS pgvector DB, index queues, index manifest table, indexer image |
| `rag-corpus-index-orchestration` | Index planner Lambda, `rag-corpus-index-run` state machine |

Reusable helpers: **Delete CloudFormation Stack** (manual dropdown of
the 6 stacks, or reusable from a workflow) and **Inspect
CloudFormation Stack** (read-only: stack status + events, failed
changeset detail, resource-existence check, Batch log fetch, RDS log
fetch). A stack in `ROLLBACK_COMPLETE` cannot be updated — delete it
first, then re-run the provision workflow.

## 12. Amazon CloudWatch

- **Batch job logs**: log group `/aws/batch/job`, stream
  `<job-name>/default/<task-id>` — the first place to look when an
  execution fails at `CustomerCase-SubmitBatchWorkers`.
- **Lambda logs**: `/aws/lambda/<function-name>`.
- **RDS logs**: the PostgreSQL error log files (see §7).
- **Alarms**: a DLQ alarm per pipeline (in the orchestration stacks).

## 13. Amazon EventBridge

No rules are created by hand. Step Functions creates an EventBridge
**managed rule** automatically when a state machine uses
`batch:submitJob.sync` — the rule watches the Batch job so the state
knows when it finishes. That is why the state machine role
(`SfnRole`) needs `events:PutRule/PutTargets/DescribeRule/DeleteRule/
RemoveTargets` on `arn:aws:events:<region>:<account>:rule/*`: without
it the state machine itself fails to create.

## 14. AWS Secrets Manager

- **`rag-corpus-index-db`** — the RDS master password. The indexer
  Batch task role reads it (`secretsmanager:GetSecretValue`); the
  worker code never logs it.
- GitHub-side secrets (not AWS) that the workflows use:
  `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`,
  `AWS_ACCOUNT_ID`, `PROJECT`.

## 15. AWS IAM

Per-stack roles (each stack creates its own):

| Role | Purpose |
|---|---|
| `PlannerRole` / `BatchTaskRole` / `BatchExecutionRole` / `BatchServiceRole` | Lambda planner, Batch task, Batch execution, Batch service |
| `SfnRole` | The state machine: invoke the planner Lambda, submit Batch jobs, create the EventBridge managed rule, write to the DLQ alarm |
| `BatchTaskRole` (indexing) | Indexer: S3 corpus access, DynamoDB index-manifest, SQS queue, `bedrock:InvokeModel`, Secrets Manager read |

Least privilege per role; the most common gap is an S3 permission the
worker needs but the role lacks (see §4 — `s3:ListBucket`).

## 16. Amazon VPC & networking

| Item | Value |
|---|---|
| VPC | `vpc-004fcdad2eea59207` (`10.0.0.0/16`), created by AWS-001 (`create-new`) |
| Subnets | 2 private subnets (`subnet-0f445b15268bfb078`, `subnet-0ad9d4199f3d0455f`) + 1 public subnet |
| NAT gateway | 1, in the public subnet (~$32/month) — Batch tasks reach S3/Bedrock/ECR through it |
| Security group | Outbound-only (`sg-06d09b6dbda12e705`) |
| RDS | In the DB subnet group, private only |

Batch tasks and RDS live in the private subnets; nothing in the data
plane has a public IP.

## 17. Amazon CloudTrail

A trail (in the storage stack) logs AWS API calls to a dedicated trail
bucket, so who did what in the account is auditable.

## 18. Checking status & troubleshooting

| Question | How to check |
|---|---|
| Did a generate/index execution finish? | Run **AWS-011 Check Run Status** (`kind` = generate/index, `format`, `year`, `run_id` or blank = latest, `wait` = true). It waits for the execution, reports its status and failure cause, and counts what actually landed (S3 documents / DynamoDB chunks). |
| Why did a Batch job fail? | Run **Inspect CloudFormation Stack** with `job_queue` + `job_name` (or `log_stream` if you know it) — it dumps the container's CloudWatch log. |
| Why is the database dropping connections? | Run **Inspect CloudFormation Stack** with `rds_instance` = `rag-corpus-index-db` — it prints the instance status and the PostgreSQL log's FATAL lines. |
| Why did a stack deploy fail? | Run **Inspect CloudFormation Stack** with the stack name — it shows the stack events and the failed changeset. |
| Did the GitHub run email me? | GitHub emails on workflow **failure** only, not on success. |

## 19. Costs (approximate)

| Item | Approx. |
|---|---|
| NAT gateway | ~$32/month |
| RDS `db.t4g.micro` | Small; the main cost driver if left running |
| Fargate Spot (Batch) | Pay per job run only |
| S3 | Storage per document; 12M files at full scale is the number to watch |
| Bedrock embeddings | Per token, per index run |

Datagen and indexing stacks stay up between runs — the resources that
cost money while idle are the NAT gateway and the RDS instance.
`AWS-010` / `AWS-Index-010` destroy the stacks when the project is done
(run the delete-data workflows first).
