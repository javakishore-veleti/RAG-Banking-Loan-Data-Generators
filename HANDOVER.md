# Handover — RAG Banking Loan Corpus (2026-11-12)

Read this first if you are picking up this project (Cursor, Claude Code,
Codex, or a human). It is the true current state as of 2026-11-12, ~22:55 EST.
GitHub issues alone do not tell the full story — see §2. The per-issue
source of truth is GIT_ISSUES_SEQUENCING.md (verified against GitHub
2026-11-12 evening: all 248 issues match).

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

Since the teardown, the code kept moving (all on main, CI green):
- F016 real-artifact seeding, F018 policy corpus and F019 natural-hash
  dedup are BUILT, pushed and their issues closed. M003 is 7 open /
  29 closed (80%). E005 epic (#5) is closed.
- The only open M003 items are E006 #6, F020 #75, F021 #78 and stories
  S047 #76, S048 #77, S049 #79, S050 #80 — all gated on live AWS runs /
  scale (see §4).
- API Services planning is done as issues: 3 new milestones M008–M010
  and 68 issues (#182–#249) for the local dev platform, the Entitlements
  API (FastAPI) and the container-image pattern. No service code yet.
- VPC decision is MADE (2026-11-12 evening): the provision workflows
  default to the account's default VPC (see §3).

## 2. Sequence, per milestone — how to read the issues

Work runs milestone by milestone, in this order. Do not start the next
milestone until the previous one's exit criteria pass.

| Milestone | Name | Status | What runs here | What gates the next one |
| M001 | Foundation & Local Generator | CLOSED (12/12) | Generator core, data model | — |
| M002 | Six Formats & Ground Truth | CLOSED (29/29) | All 6 format writers, manifest | — |
| M003 | Uniqueness & Realism | Open (7 open / 29 closed) | Uniqueness control (F013–F015, done), realism + real-artifact seeding (F016–F018, done), dedup hash (F019, done), dedup markers + audit (F020–F021, open) | Wording-only mean ≤ 0.15, same-type >0.5 ≤ 5% on 200 records; dedup audit clean |
| M004 | AWS Professional Pipeline | Open (30 open / 0 closed) | CloudFormation infra (F022–F024, F031), Batch execution (F025–F027) | One format + one year (1,000 records) runs end to end in AWS |
| M005 | Scale & Hardening | Open (20 open / 0 closed) | Quality + release (F028–F030, F032–F033) | 200k for one format + one year completes; DLQ empty; dedup audit clean; teardown + data deletion verified |
| M006 | Indexing Foundation & Pipeline | Open (14 open / 16 closed) | Indexing core, chunking, metadata, Bedrock embedder, pgvector/OpenSearch schemas | A small index run succeeds end to end |
| M007 | Indexes, Quality & Hardening | Open (18 open / 5 closed) | Planner, worker, workflows, retry/failover, testing, docs | Golden-set retrieval check (S118) passes |
| M008 | Local Development Platform | Open (26 open / 0 closed) | Postgres/Redis/ELK/RabbitMQ via docker-compose, docker-all scripts, package.json commands, uv | docker-all-up brings up all four; status healthy |
| M009 | Entitlements API Service | Open (21 open / 0 closed) | FastAPI Entitlements service: signup, signin, obtain features, roles | Local signup → signin → GET /features end to end |
| M010 | Microservice Images, Pattern & Portals | Open (21 open / 0 closed) | Microservice template, local .sh runners, CI images on main only, AWS-012 ECR publish, Loan-Advisor local startup | Entitlements image in ECR via manual AWS-012; Loan-Advisor runs locally |

Rules that GitHub cannot show you (they live here, not in the UI):
- M001 → M002 → M003 → M004 → M005, then M006 → M007, then
  M008 → M009 → M010. Do not start M004 before M003 is done. Do not
  scale to 200k/year (M005) until the M003 uniqueness numbers and the
  dedup audit (F021) are clean. Do not start M009 before M008, or M010
  before M009 (template + AWS-012 image workflow are copied from the
  Entitlements service).
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
1. VPC — DECIDED 2026-11-12 evening: use the account's default VPC.
   AWS-001 and AWS-Index-001 both offer vpc_mode default-vpc (default)
   or create-new. default-vpc finds the account's default VPC, its
   subnets and its default security group automatically — nothing to
   configure, no NAT gateway (~$32/mo saved). create-new deploys the
   $PROJECT-vpc stack with a NAT gateway instead. Pick the SAME mode in
   both workflows. No VPC_ID / SUBNET_IDS / SECURITY_GROUP_IDS secrets
   exist and none are needed.
2. Run AWS-001 Provision Infra, then AWS-Index-001 Provision Indexing.
3. Regenerate the corpus: AWS-003 (100 PDFs, 2024) for a small test.
4. Index it: AWS-Index-003, then watch it with AWS-011 Check Run Status.
5. After any teardown, run AWS-099 Double-Check Resources and confirm
   ALL CLEAR.
Secrets needed (already in GitHub): AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, AWS_REGION (= us-east-1), AWS_ACCOUNT_ID, PROJECT
(= rag-corpus). Region is us-east-1 everywhere.

## 4. Pending work and open decisions

- M003 (7 open): F020 #75 + S047 #76, S048 #77 (dedup markers,
  deterministic keys — exercised only in AWS runs, M004) and F021 #78 +
  S049 #79, S050 #80 (dedup audits — only pass at scale, M005); E006 #6
  closes when they do. F016, F018, F019 and E005 are DONE — do not redo.
- M004/M005 (50 open): not started; M004 waits on M003.
- M006/M007 (32 open): E011–E014, F037, F039, F040, F041–F044, S118 and
  their stories — all gated on a live index run.
- M008–M010 (68 open, #182–#249): local platform, Entitlements API,
  image pattern + portals. Issues created 2026-11-12; NO code yet.
  Start with M008 (Postgres compose, F047). FastAPI is the decided
  stack; local apps/portals run via .sh scripts, NOT Docker containers
  (Docker images exist for CI/AWS only); local Postgres is one server,
  database/user/password `postgres`, schema per service
  (`entitlements_db`); migrations via Alembic, run by bin/start-app.sh
  before the app starts. Roles (for now): Customer, Partner, Advisor,
  SuperAdvisor, Customer Admin, Guest User.
- Index end-to-end test (open): the last re-test never got a confirmed
  verdict — the security-group fix is in the repo (indexing.yaml,
  DBSecurityGroup) and the DB probe passed, but AWS-011's final verdict
  was never confirmed before the teardown. Re-run after rebuild. Note:
  the worker's original error ("server closed the connection") differed
  from the probe's timeout — a second issue may remain.
- API Services agents (LangChain + AWS Strands endpoints, Angular
  Loan-Advisor app): planned and documented only, no code; the
  Entitlements service gates them.

## 5. Gotchas the next agent must know

- Verify against the GitHub API (api.github.com), not browser reports —
  browser-quoted log lines have been wrong before. The anonymous API rate
  limit is 60 requests/hour per IP and gets hit often; use calls sparingly.
- Verify commit FILE PATHS via the API contents endpoint, not just
  messages and line counts — a commit's file list is repo-root-relative
  and a short path means the file landed at the repo root. (F016's seed
  files were misplaced at the root this way; the generator silently fell
  back to built-in terms and CI stayed green because the tests were never
  collected.)
- If you use the GitHub web editor: it auto-indents pasted YAML blocks.
  Verify dash indentation in the commit diff, not just content. Never fix
  indents with Backspace (each press removes a 2-space indent level).
  Full-file replacement is the reliable route for YAML files; targeted
  flag-text edits (no indent change) are safe. If you have local git
  access, push with git instead — it avoids all of this.
- CI does NOT compile scripts/*.py — a green CI does not prove the close
  scripts parse. The workflow run itself is the check.
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
- Do not close issues without the owner's approval of the list — closing
  is the status change. The close workflows (close-issues.yml,
  close-index-issues.yml) take their lists from scripts/close_issues.py
  and scripts/close_index_issues.py.
