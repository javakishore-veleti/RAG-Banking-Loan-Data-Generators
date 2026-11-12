# Handover — RAG Banking Loan Corpus (2026-11-12)

Read this first if you are picking up this project (Cursor, Claude Code,
Codex, or a human). It is the true current state as of 2026-11-12 evening.
GitHub issues alone do not tell the full story — see §2.

## 1. Current state — everything in AWS is deleted

On 2026-11-12 the owner asked for a full teardown ("tear everything down
now — stop all charges"). It completed the same day and was verified twice:
- All 6 CloudFormation stacks are gone: rag-corpus-vpc, rag-corpus-storage,
  rag-corpus-compute, rag-corpus-orchestration, rag-corpus-indexing,
  rag-corpus-index-orchestration.
- Both S3 buckets are gone (corpus + CloudTrail log bucket), including all
  object versions. The 100 generated PDFs, manifests and index markers are
  gone and are not recoverable — regenerate them (see §3).
- The RDS PostgreSQL database, both ECR repos, DynamoDB tables, SQS queues,
  Lambda functions, Step Functions machines and Batch resources are gone.
- AWS-099 Double-Check Resources run #1 (2026-11-12) printed ALL CLEAR:
  27 checks, zero leftovers.
- What remains: all the code in this repo, and the owner's pre-existing
  CDKToolkit stack (October 2026, not part of this project — leave it alone).
- Cost now: ~$0/month. Nothing is running.

## 2. Sequence, per milestone — how to read the issues

Work runs milestone by milestone, in this order. Do not start the next
milestone until the previous one's exit criteria pass.

| Milestone | Name | Status | What runs here | What gates the next one |
| M001 | Foundation & Local Generator | CLOSED (12/12) | Generator core, data model | — |
| M002 | Six Formats & Ground Truth | CLOSED (29/29) | All 6 format writers, manifest | — |
| M003 | Uniqueness & Realism | Open (20 open / 16 closed) | Uniqueness control (F013–F015), realism + real-artifact seeding (F016–F018), dedup design + hash + audit (F019–F021) | Wording-only mean ≤ 0.15, same-type >0.5 ≤ 5% on 200 records; dedup audit clean |
| M004 | AWS Professional Pipeline | Open (30 open / 0 closed) | CloudFormation infra (F022–F024, F031), Batch execution (F025–F027) | One format + one year (1,000 records) runs end to end in AWS |
| M005 | Scale & Hardening | Open (20 open / 0 closed) | Quality + release (F028–F030, F032–F033) | 200k for one format + one year completes; DLQ empty; dedup audit clean; teardown + data deletion verified |
| M006 | Indexing Foundation & Pipeline | Open (14 open / 16 closed) | Indexing core, chunking, metadata, Bedrock embedder, pgvector/OpenSearch schemas | A small index run succeeds end to end |
| M007 | Indexes, Quality & Hardening | Open (18 open / 5 closed) | Planner, worker, workflows, retry/failover, testing, docs | Golden-set retrieval check (S118) passes |

Rules that GitHub cannot show you (they live here, not in the UI):
- M001 → M002 → M003 → M004 → M005. Do not start M004 before M003 is
  done. Do not scale to 200k/year (M005) until the M003 uniqueness numbers
  and the dedup audit (F021) are clean.
- Inside an epic, the IDs are the order: F019 → F020 → F021,
  S044 → S050. GitHub sorts issues by created/updated date, not by
  sequence — the IDs are the sequence.
- Delete data BEFORE destroy infra: run AWS-009 (or AWS-Index-009) before
  AWS-010 (or AWS-Index-010). CloudFormation cannot delete a non-empty
  S3 bucket.

### Why E006 (Deduplication) looks overlapped across milestones

The plan doc lists E006 as "M003–M005". That is the capability's
lifecycle, not its issue assignment: every E006 issue (epic #6, features
F019 #71, F020 #75, F021 #78, stories S044–S050 #72–#80) sits in M003.
The work matters across three phases — F019 defines the natural key and
hash (M003, with the uniqueness work), F020's shard markers and atomic
claims only get exercised when runs execute in AWS (M004), and the F021
audit only passes at scale (M005) — so M005's exit criteria require the
dedup audit to be clean even though the audit issue lives in M003. That
is the whole overlap: one epic, three phases, one milestone for the
issues. Do not re-split it without the owner's say-so.

## 3. Rebuild path (after the teardown)

Nothing is deployed. To get back to a working system:
1. Decide the VPC first (unresolved — see §4). AWS-001's vpc_mode defaults
   to create-new (builds a VPC + NAT gateway ~$32/mo). use-existing reuses
   a VPC from the VPC_ID / SUBNET_IDS / SECURITY_GROUP_IDS secrets.
2. Run AWS-001 Provision Infra, then AWS-Index-001 Provision Indexing.
3. Regenerate the corpus: AWS-003 (100 PDFs, 2024) for a small test.
4. Index it: AWS-Index-003, then watch it with AWS-011 Check Run Status.
5. After any teardown, run AWS-099 Double-Check Resources and confirm
   ALL CLEAR.
Secrets needed (already in GitHub): AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, AWS_REGION (= us-east-1), AWS_ACCOUNT_ID, PROJECT
(= rag-corpus). Region is us-east-1 everywhere.

## 4. Pending work and open decisions

- VPC decision (open): default VPC or create-new. Blocks any rebuild.
- Index end-to-end test (open): the last re-test never got a confirmed
  verdict — the security-group fix is in the repo (indexing.yaml,
  DBSecurityGroup) and the DB probe passed, but AWS-011's final verdict
  was never confirmed before the teardown. Re-run after rebuild.
- M003 (20 open): F016 real-artifact seeding, F018 policy corpus
  generator, F019–F021 dedup (designed, not built).
- M004/M005 (50 open): not started; M004 waits on M003.
- M006/M007 (32 open): E011–E014, F037, F039, F040, F041–F044, S118 and
  their stories — all gated on a live index run.
- API Services (LangChain + AWS Strands agents, Angular Loan-Advisor app):
  planned and documented only, no code.

## 5. Gotchas the next agent must know

- Verify against the GitHub API (api.github.com), not browser reports —
  browser-quoted log lines have been wrong before. The anonymous API rate
  limit is 60 requests/hour per IP and gets hit often; use calls sparingly.
- The GitHub web editor auto-indents pasted YAML blocks. Verify dash
  indentation in the commit diff, not just content. Never fix indents with
  Backspace (each press removes a 2-space indent level). Full-file
  replacement is the reliable route for YAML files; targeted flag-text
  edits (no indent change) are safe.
- GitHub `workflow_call` inputs REQUIRE a `type`, and `type: number`
  rejects string values passed from `workflow_dispatch` inputs — use
  `type: string` for values only interpolated into shell/JSON text.
- `aws s3 rm --recursive` does NOT delete object versions. Both corpus
  buckets are versioned: emptying must delete every version and delete
  marker (see the empty_bucket function in AWS-009) and must include the
  trail bucket, or the storage stack delete fails.
- AWS Batch has NO `aws batch wait` subcommand — poll with
  `describe-jobs` instead (see AWS-Index-009).
- Lambda reserves the `AWS_REGION` env var — never set it on a Lambda
  function. Step Functions `batch:submitJob.sync` needs EventBridge
  permissions on the SfnRole or the state machine fails to create.
- A CloudFormation stack in ROLLBACK_COMPLETE must be deleted before it
  can be redeployed. Use the reusable delete-cloudformation-stack
  workflow, not the AWS console.
- Never ask the owner to sign in to the AWS console or configure subnets.
  Use the GitHub secrets through reusable workflows. Never ask him to pick
  the embedding model by editing config — the options live in the Actions
  run UI with a default.
- Bedrock model access is retired — Titan Text Embeddings V2 activates on
  first InvokeModel. There is nothing to enable.
- State how long a long push or run should take before it starts; the
  owner has cancelled work he thought was stuck.
- The owner is Kishore. Call him Kishore, not Veleti.
