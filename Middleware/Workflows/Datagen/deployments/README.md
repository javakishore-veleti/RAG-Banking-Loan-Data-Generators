# Datagen deployments

One app, one image, one set of stacks. Nothing here is shared
with a future API service or portal — those get their own
Dockerfile and their own deployments under their own folders.

## Docker image

- **Image:** `<project>-worker` (ECR), built from this folder as
  the Docker build context: `docker build -f Dockerfile .`
- **Base:** `python:3.12-slim` + boto3 + Pillow (`requirements.txt`).
- **Entrypoint:** `src/worker/batch_worker.py` — polls SQS until
  the queue is empty, generates a 10k-record shard, uploads to
  S3 + DynamoDB.
- **Built by:** the `aws-001-provision-infra.yml` workflow (root
  `.github/workflows/`), which pushes `:latest` and the commit
  SHA tag to ECR. Rebuild on every infra deploy; the Batch job
  definition always points at `:latest`.

## CloudFormation stacks (deploy order)

Deployed by `aws-001-provision-infra.yml`, all manual:

1. `<project>-storage` — `infra/cloudformation/storage.yaml`
   (S3 corpus bucket, DynamoDB manifest + dedup, SQS FIFO + DLQ,
   CloudTrail + trail bucket).
2. `<project>-compute` — `infra/cloudformation/compute.yaml`
   (ECR, Batch Fargate Spot, job queue + definition; VPC/subnets/
   security groups come from GitHub Secrets as parameters).
3. `<project>-orchestration` — `infra/cloudformation/orchestration.yaml`
   (Planner Lambda, Step Functions, DLQ alarm).

## Data generation (runtime)

Triggered manually, one workflow per format, from the repo root:
`.github/workflows/generate-<format>.yml` → shared reusable
`aws-002-generate.yml` → Step Functions → Planner Lambda → SQS →
AWS Batch (this image) → S3 + DynamoDB.

## Teardown (end of life, in order)

1. `aws-009-delete-data.yml` — empties the S3 corpus bucket, deletes
   DynamoDB tables + SQS queues; CloudTrail last, so the
   deletion itself is audited.
2. `aws-010-destroy-infra.yml` — deletes the stacks in reverse order
   (orchestration → compute → storage → vpc), ECR images first.
   The vpc stack only exists if AWS-001 ran with `vpc_mode=create-new`.
