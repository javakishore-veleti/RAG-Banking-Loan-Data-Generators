# DESIGN — RAG Corpus (Banking Loans)

> Companion to `README.md` (how to use it) and `ARCHITECTURE.md`
> (how it is built). This document records *why* it is designed this
> way: the decisions, the data model, the interfaces, the invariants,
> and the trade-offs. If you change a decision, change this document
> in the same commit, and say why.

---

## Table of contents

1. [Design principles](#1-design-principles)
2. [What problem this solves](#2-what-problem-this-solves)
3. [Data model — customer records vs policy documents](#3-data-model--customer-records-vs-policy-documents)
4. [Generator design](#4-generator-design)
5. [Uniqueness design — descriptions, not demographics](#5-uniqueness-design--descriptions-not-demographics)
6. [Deduplication design — unique fields, not just PK](#6-deduplication-design--unique-fields-not-just-pk)
7. [Interfaces and schemas](#7-interfaces-and-schemas)
8. [S3 partitioning design](#8-s3-partitioning-design)
9. [Workflow design — per format, shared bottom layer](#9-workflow-design--per-format-shared-bottom-layer)
10. [Security and secrets design](#10-security-and-secrets-design)
11. [Testing strategy](#11-testing-strategy)
12. [Invariants — things that must always stay true](#12-invariants--things-that-must-always-stay-true)
13. [Extensibility — how to add things](#13-extensibility--how-to-add-things)
14. [Open questions and future work](#14-open-questions-and-future-work)
15. [Decision log](#15-decision-log)
16. [Indexing design — layers, metadata, embedding models](#16-indexing-design--layers-metadata-embedding-models)

---

## 1. Design principles

1. **Ground truth first.** Every generated document must carry its
   question and answer in the manifest. A corpus you cannot measure
   against is not a test corpus.
2. **Uniqueness is a precondition, not polish.** If descriptions
   overlap too much, RAG retrieval is meaningless. Enforce uniqueness
   in the generator, measure it before scaling. See §5.
3. **Determinism over cleverness.** Same seed + start + year =
   same records, same files. Determinism is what makes retries safe
   and runs reproducible.
4. **Shard everything.** No single job should own 1M records. Shards
   are the unit of parallelism, retry, and resume.
5. **One shared bottom layer.** Per-format code is a thin wrapper
   only. Logic lives once, in the generator / worker / planner.
6. **Manual triggers for expensive work.** Nothing that costs real
   money runs on a schedule or on push. Provisioning and generation
   are both manual `workflow_dispatch` actions.
7. **Secrets never in the repo.** VPC, credentials, and account IDs
   come from GitHub Secrets and CloudFormation parameters.
8. **Docs are the contract.** `README.md`, `ARCHITECTURE.md`, and
   this file describe intent. Code follows them. Cursor (or any
   developer) should read them before changing code.

---

## 2. What problem this solves

A RAG system for banking loans needs a corpus to retrieve from. Real
customer documents are not available at scale, and the documents that
*are* public (blank forms, regulations, product pages) do not cover
the question space — loan customers, support, and partners asking
about specific loans.

So the corpus is *synthesised*: realistic loan records, rendered in
the six formats a real bank actually produces, with known questions
and answers. The corpus exists to let you:

- Build a RAG pipeline end to end and see it work on real formats.
- Measure retrieval (recall@k, precision) and grounding (is the
  answer in the retrieved document?) against ground truth.
- Stress-test parsers (PDF, DOCX, XLSX, OCR on PNG) and scaling
  (millions of files, partitioned by year).
- Learn RAG properly: the goal is *RAG Mastery* — mastery means
  being able to measure and fix retrieval, not just generate text.

The corpus is **not** production data, and a RAG system trained or
evaluated only on it is not production-ready. Real anonymised
internal documents must replace it through the same pipeline later.

---

## 3. Data model — customer records vs policy documents

This distinction caused real confusion during design, so it is
recorded here explicitly.

### 3.1 Customer-like records (what this repo generates)

- **One record = one loan.** Customer, amount, rate, tenure, EMI,
  status, branch, start date, channel, plus one question + answer
  about that loan.
- **Volume:** 200,000 per annum, 10 years = 2,000,000 per format.
- **Description-based:** each document is a natural-language
  description/summary of that loan. The CSV/XLSX versions are the
  same description in tabular form — the text is the point, because
  RAG retrieval is text-based.
- **Example question:** "What is the interest rate for a business
  loan?" — answered from that loan's record.

### 3.2 Policy documents (not generated here — yet)

- **One document = one rule** that applies to thousands of loans:
  rate policy, eligibility rules, prepayment rules, MITC, effective
  dates, versioned over time.
- **Volume:** tens to hundreds, not millions. 200,000 copies of the
  same policy would be duplicate content that drowns retrieval.
- **Relationship:** a customer record *references* a policy version
  (e.g. `policy_version: home-v2024-01`). The RAG system needs both
  corpora to answer "what is the rate?" (customer record) and "what
  is the policy?" (policy document).
- **Future work:** a separate, small, versioned policy generator.
  See §14.

### 3.3 Loan types and ranges

| Loan type | Amount range | Rate range | Tenures (months) |
|---|---|---|---|
| Home Loan | 500k–15M | 8.5–11.5% | 120, 180, 240, 300 |
| Personal Loan | 50k–1.5M | 10.5–16.0% | 12, 24, 36, 48, 60 |
| Business Loan | 500k–50M | 9.0–15.0% | 12, 24, 36, 60, 84 |
| Auto Loan | 200k–3M | 8.0–12.0% | 12, 24, 36, 48, 60 |
| Education Loan | 100k–5M | 9.5–13.5% | 60, 84, 120, 180 |
| Gold Loan | 25k–2M | 9.0–14.0% | 6, 12, 18, 24 |
| MSME Loan | 100k–10M | 8.75–14.5% | 12, 24, 36, 60 |

Amounts use a log-uniform distribution within the range (clustered,
like real loan amounts), not uniform random. Rates and tenures are
chosen from the loan type's realistic ranges. EMI is computed, not
random: `EMI = P·r·(1+r)^n / ((1+r)^n − 1)`, `r` monthly.

All names, branches, and IDs are fictional.

---

## 4. Generator design

**File:** `Middleware/Workflows/Datagen/src/generator/generator.py`. No external dependencies for
PDF/DOCX/XLSX/CSV/TXT. Pillow is optional, for PNG text cards.

### 4.1 One record, six renderings

`make_record(rng, i, year=None)` returns a dict (see README §4).
`lines_for(rec)` returns the description lines. Each writer
(`write_pdf`, `write_docx`, `write_xlsx`, `write_csv`, `write_txt`,
`write_png`) renders those same lines in its format:

- PDF: minimal hand-written PDF (Helvetica, one page) — no ReportLab
  dependency, so the generator runs anywhere.
- DOCX / XLSX: hand-built OOXML zip archives (no `python-docx` /
  `openpyxl` dependency at generation time; those libraries are used
  only in tests to verify the output parses).
- CSV: one row per record, with the full question + answer.
- TXT: the description lines, plain text.
- PNG: Pillow `ImageDraw` loan summary card (or a plain PNG fallback
  without Pillow).

**Why hand-built OOXML/PDF instead of libraries?** Portability.
The generator must run in a minimal Docker image, in Lambda, and on
a developer's laptop with nothing installed. Libraries are a
convenience, not a requirement, for these formats.

### 4.2 Determinism

`rng = random.Random(seed)` in the CLI, and in the Batch worker
`rng = random.Random(seed × 1_000_003 + start + year × 10_007)`.
The worker's formula means a shard's RNG does not depend on
advancing through all previous records — it is O(1) per shard, and
a retry reproduces identical records.

**Consequence:** `loan_id` is derived from the RNG + index, so it is
deterministic for a given seed/start/year. Change the seed and you
get a different corpus; keep the seed and you get the same corpus.

### 4.3 Adding a format

1. Add a `write_<fmt>(path, rec)` function in `generator.py`.
2. Add it to the `WRITERS` dict.
3. Add one thin workflow `.github/workflows/generate-<fmt>.yml`
   (copy `aws-003-generate-pdf.yml`, change the format name).
4. Add the format to the README format table and to `DESIGN.md §3`.
5. Add a test that the output parses (see `Middleware/Workflows/Datagen/tests/test_generator.py`).

Do not add per-format logic to the planner, worker, or Step Functions
— they are format-agnostic by design.

---

## 5. Uniqueness design — descriptions, not demographics

**The correction that shaped this design:** the duplicate concern
here is *not* demographics (names, ages), *not* primary keys, and
*not* unique data fields. It is the synthetic *descriptions
themselves*: how unique is each generated description, and how much
overlap is there between descriptions?

### 5.1 Why it matters

If descriptions overlap too much, later RAG is useless:

- Retrieval returns any of thousands of near-identical documents,
  usually the wrong loan, with the wrong rate/EMI.
- The LLM mixes facts from several near-identical documents.
- Evaluation is meaningless: the right document and the wrong
  documents are indistinguishable, so recall/precision scores prove
  nothing.
- Scale is fake: 1M overlapping descriptions is effectively a few
  hundred templates repeated.

### 5.2 How it is measured

Metric: **wording-only Jaccard similarity on word 5-gram shingles,
digits stripped.** Two descriptions that differ only in numbers
score near 1.0. Tool: `Middleware/Workflows/Datagen/uniqueness_check.py`.

Measured (200 records, seed 7):

| Metric | v1 | v2 (current) |
|---|---|---|
| Wording-only mean | 0.246 | 0.128 |
| Wording-only, same loan-type mean | 0.333 | 0.167 |
| Same-type pairs > 0.5 | 25.0% | 1.5% |
| Max | 0.882 | 0.701 |

### 5.3 How v2 achieves it

1. **Four paraphrase variants per answer topic**, chosen per record
   (`rec["variant"]`). Same facts, different words.
2. **Three layouts** (`rec["layout"]`): standard, question-first,
   status-first, with fields in different orders.
3. **Varied field labels**: `Amount` / `Sanctioned amount`,
   `EMI` / `Monthly instalment`, `Interest Rate` / `Rate charged`.
4. **One contextual sentence per record**, from channel / purpose /
   status.
5. **Generate → measure → reject loop** in the CLI:
   `--max-overlap 0.65` (default). A description whose wording-only
   5-gram Jaccard vs already-kept descriptions exceeds 0.65 is
   regenerated with a different variant/layout, up to 5 attempts.
   In the 200-record run, 3 descriptions were rejected/regenerated.

### 5.4 Limits

- The remaining overlap is mostly unavoidable domain vocabulary
  (interest rate, EMI, tenure, loan type). 100% unique text is not
  achievable — or desirable — in one domain.
- The pairwise checker is O(n²) and is only for samples (≤200).
  At 1M scale, use MinHash/LSH in the Batch worker, with the
  dedup table as the claim store.
- This check is wording-only. It does not measure embedding cosine
  similarity. Add that as a second check before production use.

---

## 6. Deduplication design — unique fields, not just PK

There are three different duplicates. Each has a different guard.

### 6.1 Same shard retried

Guard: S3 `.done` marker + deterministic S3 keys. A replay skips
finished shards; unfinished shards regenerate identical files.

### 6.2 Same SQS message delivered twice

Guard: SQS FIFO deduplication (`MessageDeduplicationId =
run_id + shard_id`, 5-minute window) + idempotent writes
(deterministic keys, DynamoDB upserts with identical values).

### 6.3 Same unique business fields under a different ID

This is the subtle one. A surrogate PK (`doc_id`) cannot stop it:
two records can have identical unique fields and different `doc_id`s.

**Design:**

1. **Define the unique field set first** (a business decision, not
   a technical one). Example candidates:
   - `(customer_id, loan_type, start_date)`
   - `(loan_account_number)` alone
   - Full content: `(customer, loan_type, amount, rate, tenure, start_date)`
2. **Normalise** the fields (lowercase, trim, round amounts/rates,
   format dates identically).
3. **Hash:** `natural_hash = SHA256(normalised fields joined by |)`.
4. **Claim atomically** in the dedup table, whose PK *is*
   `natural_hash`:
   `PutItem, ConditionExpression: attribute_not_exists(natural_hash)`.
   The first writer wins; the second gets a conditional-check
   failure and skips the file.
5. **S3 key includes the hash** (or the natural key), so identical
   content lands on the identical object.

**What does not work:**

- A GSI in DynamoDB does **not** enforce uniqueness. Only a PK
  (and sort key) does.
- Checking "does this exist?" then writing is racy across parallel
  workers. The conditional `PutItem` is the atomic operation.
- Near-duplicates (typos, rounding differences) will not hash
  identically. Normalise first; for fuzzy near-duplicates, use
  MinHash/LSH (§5) instead of an exact hash.

**Generation-time prevention is better than post-hoc dedup:** the
generator should sample unique tuples *without replacement* where
possible, so duplicates are never emitted. The dedup table is the
safety net for parallel shards that cannot see each other's seen-set.

**Audit:** after a run, `GROUP BY <unique fields> HAVING COUNT(*) > 1`
in Athena/Glue. If it returns rows, there are duplicates even with
different PKs.

---

## 7. Interfaces and schemas

### 7.1 Step Functions input (one format + year per run)

```json
{
  "total_per_format": 200000,
  "shard_size": 10000,
  "formats": ["pdf"],
  "year": 2024,
  "seed": 7,
  "run_id": "2024-pdf-20261112-083000"
}
```

### 7.2 Planner output

```json
{
  "run_id": "2024-pdf-20261112-083000",
  "formats": ["pdf"],
  "year": 2024,
  "shards_enqueued": 20,
  "shards": [{"shard_id": "shard-0000", "start": 0, "count": 10000,
              "formats": ["pdf"], "year": 2024, "seed": 7,
              "run_id": "2024-pdf-20261112-083000"}]
}
```

### 7.3 SQS shard message

Same shape as one element of `planner.shards`. `MessageDeduplicationId`
is `run_id + "-" + shard_id`; `MessageGroupId` is `run_id`.

### 7.4 S3 key schema

```
raw/<format>/year=YYYY/month=MM/day=DD/loan_<idx:07d>_<loan_id>.<ext>
manifests/<run_id>/<shard_id>.jsonl
markers/<run_id>/<shard_id>.done
lambda/planner.zip
```

### 7.5 DynamoDB manifest item

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

### 7.6 Dedup table item

```json
{ "natural_hash": "<sha256 hex>", "doc_id": "pdf_0000000",
  "run_id": "2024-pdf-20261112-083000" }
```

### 7.7 Generator CLI

```
--count N --out DIR --seed S --formats a,b,c --start N
--year YYYY --max-overlap 0.65
```

See `README.md §2` for full options.

---

## 8. S3 partitioning design

**Decision:** partition by loan start date, Hive-style:
`year=YYYY/month=MM/day=DD/`.

**Why loan date, not generation date:** the partition should answer
"all loans from 2024", not "all files generated on Tuesday". A run
for 2024 writes only into `year=2024/` partitions, so per-year runs,
queries, and lifecycle rules are prefix operations.

**Why Hive-style (`year=`) instead of plain `2024/03/12/`:** Athena
and Glue understand `year=` partitions directly. Plain paths work
for S3 listing, but need manual partition registration for Athena.

**Why not partition by format first, then date?** That is what we
do: `raw/<format>/year=…/…`. Format is the top level because
workflows, parsers, and ingestion are per format. Date is the second
level because runs and queries are per year.

**Trade-off:** very small files (one record per file) are inefficient
for Athena/Glue scans — that is intentional. RAG ingestion needs
individual documents, not Parquet bundles. If you later need
analytics, build a separate Parquet export from the manifest.

---

## 9. Workflow design — per format, shared bottom layer

**Decision:** six manual per-format workflows + one shared reusable
workflow, instead of one workflow with a format matrix, or six
fully duplicated workflows.

**Why:**

- **Manual per format** matches how the work is actually done:
  one format + one year at a time, checked before the next. A
  matrix run that starts all six formats at once would hide a
  failure in one format behind five successes.
- **Shared reusable workflow** (`aws-002-generate.yml`, `workflow_call`)
  means the trigger logic, AWS auth, and Step Functions call exist
  once. A bug fix there fixes all six formats.
- **Thin wrappers** (`aws-003-generate-pdf.yml`, …) contain only the format
  name and the dispatch inputs. If a wrapper grows logic, move that
  logic down to `aws-002-generate.yml` or to the planner/worker.

**Provisioning is separate and manual** (`aws-001-provision-infra.yml`):
infra changes are rarer and riskier than data runs, and they should
not happen as a side effect of generating data.

**CI is separate** (`ci.yml`): tests run on push/PR with no AWS
access. CI never provisions infra or generates data.

---

## 10. Security and secrets design

**Current design (as chosen by the repo owner):** long-lived AWS
access keys stored as GitHub Secrets, used by the workflows via
`aws-actions/configure-aws-credentials`. VPC, subnets, and security
groups are also GitHub Secrets, passed as CloudFormation parameters.

**Trade-off — OIDC is stronger:** GitHub OIDC (no stored keys,
short-lived tokens, scoped to the repo + branch) removes the risk
of a leaked long-lived key. It requires an IAM identity provider
and role trust policy in AWS, which is more setup. If you switch,
change only the `configure-aws-credentials` steps to
`role-to-assume: <OIDC role ARN>` and remove the two key secrets.
No other code changes.

**Least privilege:** each IAM role is scoped to its job (see
`ARCHITECTURE.md §8`). The Batch task role is the broadest and is
still limited to the corpus bucket, the two DynamoDB tables, and
the shards queue.

**Data:** all generated data is synthetic/fictional. The design
assumes no real PII ever enters the generator. If that assumption
changes, the whole pipeline needs a PII review before use.

---

## 11. Testing strategy

| Layer | What is tested | How |
|---|---|---|
| Generator (unit) | EMI calculation, determinism per seed, record fields, answer mentions loan ID | `Middleware/Workflows/Datagen/tests/test_generator.py` (pytest, or manual runner in README §11) |
| Generator (output) | DOCX/XLSX parse with `python-docx` / `openpyxl`; PDF starts with `%PDF-1.4`; PNG starts with PNG magic | Manual verification in the sample run; add to tests when adding a format |
| Uniqueness | Wording-only Jaccard on a 200-record sample | `Middleware/Workflows/Datagen/uniqueness_check.py --count 200 --seed 7` — run after any generator change |
| Workflows / CFN | YAML parses (with CFN tags handled); JSON parses | CFN-aware YAML loader in validation; `py_compile` for Python |
| End-to-end (local) | 10 records, all formats, manifest written | `Middleware/Workflows/Datagen/src/generator/generator.py --count 10 --out /tmp/corpus --year 2024` |
| End-to-end (AWS) | 1,000 records, one format, one year; S3 + DynamoDB counts match | Manual generate workflow, then count S3 prefix + DynamoDB by `run_id` |

**What is not tested yet:** actual CloudFormation deployment
(no AWS account connected), Batch execution at 10k shards, Spot
interruption handling, DLQ replay at scale. Those are first-run
verification steps, not unit tests.

---

## 12. Invariants — things that must always stay true

1. Same seed + start + year ⇒ same records, same files. Never
   introduce wall-clock time, randomness without a seed, or
   unordered iteration into record generation.
2. One record ⇒ one question + one answer, identical in all six
   formats. A format must never invent or drop facts.
3. S3 key ⇒ deterministic from format + loan start date + loan ID.
   Never include a run timestamp or a random suffix in a data key.
4. A shard that finishes writes its `.done` marker. A shard without
   a marker is not finished, even if some of its files exist.
5. An SQS message is deleted only after its whole shard succeeds.
6. Secrets, VPC IDs, and account IDs never appear in the repo,
   in code, in docs examples (except placeholders), or in logs.
7. After any generator change, the uniqueness numbers in
   `README.md §5` must be re-measured. A regression (wording-only
   mean above ~0.15, same-type >0.5 above ~5%) blocks scaling.
8. Per-format logic lives only in the generator writer and the thin
   workflow wrapper. Nothing else is per-format.

---

## 13. Extensibility — how to add things

- **Seventh format:** see `README.md §3` / `DESIGN.md §4.3`.
- **New loan type:** add an entry to `LOAN_TYPES` (ranges, tenures,
  purposes) and questions to `QUESTIONS`. Re-run uniqueness.
- **New question topic:** add a topic to `QUESTIONS` and four
  paraphrase variants in `answer_for`. Re-run uniqueness.
- **Policy corpus:** new generator module (`Middleware/Workflows/Datagen/src/policy/`), new
  S3 prefix `policy/<loan_type>/version=…/`, new DynamoDB table or
  the same manifest with `record_kind: policy`. Do not reuse the
  customer record generator for policies — the volume and versioning
  are different.
- **MinHash dedup at scale:** replace the pairwise check in the
  worker with MinHash signatures stored in the dedup table, and
  claim via the hash. Keep the exact-hash claim as a fallback.
- **OIDC instead of keys:** see §10.
- **Combined multi-format run:** a new workflow that calls
  `aws-002-generate.yml` six times (once per format). Do not add a matrix
  to the existing per-format workflows.

---

## 14. Open questions and future work

1. **What is the business natural key?** The dedup design (§6)
   needs the unique field set named. Candidates are listed there;
   the repo owner needs to confirm one.
2. **Policy corpus:** design the versioned policy generator (§3.2).
3. **Embedding-based uniqueness:** add cosine similarity as a
   second uniqueness check, alongside 5-gram Jaccard.
4. **Cost measurement:** measure one 10k shard (time, vCPU-hours,
   S3 size) before committing to 200k/year.
5. **First CloudFormation deployment:** the templates are validated,
   not applied. The first provision run is the real test.
6. **RAG retrieval stage:** indexing (chunking, embedding, vector
   store) is now built — see §16. Retrieval and answering (hybrid
   search, self-query, decomposition, reranking, agents) belong to
   the API-Services phase, as two endpoints: LangChain agent and
   AWS Strands agent.
7. **First indexing deployment:** the indexing templates are
   validated, not applied. The first `aws-index-001-provision` run
   is the real test.

---

## 15. Decision log

| Date | Decision | Why | Alternatives rejected |
|---|---|---|---|
| 2026-11-12 | Synthetic generation, not downloading real docs | No matched 1M-per-format real corpus exists; real customer docs are not available at scale | Downloading public forms only (too small, unmatched formats) |
| 2026-11-12 | One record, six formats, same facts | Lets retrieval be compared across parsers with known ground truth | Separate corpora per format (no cross-format ground truth) |
| 2026-11-12 | AWS Batch (Fargate Spot), not Lambda-only | Shards run longer than Lambda's 15-min limit; Batch is built for long, parallel, heavy work | Lambda-only, Glue (poor for binary formats) |
| 2026-11-12 | CloudFormation, not Terraform | Repo owner chose AWS-native provisioning via GitHub Actions | Terraform (archived, functionally equivalent) |
| 2026-11-12 | Manual per-format workflows + shared reusable workflow | One format+year at a time, checked before the next; no duplicated logic | One matrix workflow (hides per-format failures), six duplicated workflows |
| 2026-11-12 | S3 `year=/month=/day=` by loan date | Per-year runs, queries, and lifecycle are prefix operations; Athena understands Hive partitions | Flat keys, generation-date partitions |
| 2026-11-12 | Uniqueness enforced in the generator (paraphrases + layouts + reject loop) | Without unique descriptions, RAG retrieval is meaningless — measured, not assumed | Template-only generation (25% same-type pairs >0.5 overlap) |
| 2026-11-12 | Dedup on natural-hash PK, not manifest PK | Surrogate PKs cannot stop same-fields-different-ID duplicates; only a PK on the hash can | GSI uniqueness (does not exist), post-hoc dedup only |
| 2026-11-12 | GitHub Secrets for AWS + VPC | No secrets in the repo; VPC details are deployment-specific | Hard-coding, OIDC (stronger, more setup — see §10) |
| 2026-11-12 | No chunking / ingestion in this repo | Chunking belongs to the ingestion stage, after the corpus exists | Mixing generation and ingestion in one repo |
| 2026-11-12 | Indexing as a separate app (Middleware/Workflows/DataIndexing), own image, own stacks | Same platform rule as Datagen: one app, one image, one set of stacks; retrieval reads indexes, never the generator | Bolting indexing onto Datagen's image and stacks (couples two lifecycles) |
| 2026-11-12 | Five indexing layers L0–L4, one index per layer (IDX-1…IDX-4) | Mirrors the reference video's layers; each layer is independently testable and replaceable | One monolithic "index everything" step (untestable, unreusable) |
| 2026-11-12 | pgvector is the source of truth; OpenSearch BM25 is optional and best-effort | Hybrid search needs both, but a learning setup should work with vector search alone; unsynced OpenSearch rows are retried, never blocking | OpenSearch mandatory (cost + a second source of truth to keep in sync) |
| 2026-11-12 | Embedding model per document type, default if none configured | One config file (`config/embedding_models.yaml`); resolution workflow input → per-format override → default | One model hard-coded in code (no per-format tuning, no override path) |
| 2026-11-12 | Deterministic chunk ids (`sha1(doc_id:chunk_index:model)`) | Re-runs upsert instead of duplicating; a re-embed with a new model creates new ids, so old vectors are never overwritten | Random UUID chunk ids (every re-run duplicates) |
| 2026-11-12 | `latest` flag = newest version per loan | Follows the video's stale-version fix: retrieval must prefer the current version and never silently mix old rules | No versioning (old policy versions answer as if current) |
| 2026-11-12 | Bedrock failover to the default model, once, on AccessDenied/Validation/NotFound | A missing model enablement must not kill a whole run; the model actually used is recorded per chunk | Fail the run on the first rejected model (brittle for a learning setup) |
| 2026-11-12 | Indexing reuses AWS-001's VPC by default | One VPC for the whole platform; Datagen stays the VPC owner and its AWS-010 deletes it | A second VPC per app (double NAT cost, double config) |

---

## 16. Indexing design — layers, metadata, embedding models

DataIndexing (`Middleware/Workflows/DataIndexing/`) reads the corpus
Datagen wrote to S3 and builds the indexes the future API Services
will retrieve from. It follows the reference video's layers
(Balaji Chippada, "Build Production-Ready Advanced RAG From
Scratch": 10 NIST PDFs → Docling → 500/100 splitter → metadata
enrichment with `latest=true/false` → OpenAI embeddings → pgvector;
baseline RAG fixed by hybrid search + self-query + decomposition +
reranker).

### 16.1 Index schemas

- **IDX-1 `documents`** — `doc_id` (PK), `loan_id`, `loan_type`,
  `format`, `year`, `policy_version`, `latest`, `source_s3_key`,
  `indexed_at`. One row per source document.
- **IDX-2 `chunks`** — `chunk_id` (PK, deterministic
  `sha1(doc_id:chunk_index:model_slug)`), `doc_id` (FK),
  `chunk_index`, `content`, plus the same filterable metadata as
  IDX-1 (`loan_type`, `year`, `latest`, `policy_version`,
  `embedding_model`, `opensearch_synced`).
- **IDX-3 `chunk_embeddings_<model slug>`** — `chunk_id` (PK/FK),
  `embedding vector(<dims>)`, HNSW index with
  `vector_cosine_ops`. One table per embedding model, so a model
  change creates a new table instead of mixing dimensions.
  `model_slug` is the model id lower-cased and sanitised, e.g.
  `amazon.titan-embed-text-v2:0` → `titan_v2`.
- **IDX-4 `loan-chunks-bm25`** (OpenSearch Serverless, optional) —
  same chunk content + metadata, for BM25 keyword search in hybrid
  retrieval. Dual-written best-effort; rows with
  `opensearch_synced=false` are retried on the next run.

### 16.2 Metadata — why it is a first-class layer

Self-query filtering (the video's fix for "wrong version answers")
only works if the metadata exists at index time: `latest` (newest
version per loan), `policy_version`, `loan_type`, `year`, `format`.
Metadata is enriched in L2 — before embedding — so the embedding
model and the stores never have to know where it came from.

### 16.3 Embedding model configuration

`config/embedding_models.yaml`:

- `default_model`: `amazon.titan-embed-text-v2:0` (1024 dims).
- Per-format overrides (`pdf`, `docx`, `xlsx`, `csv`, `txt`, `png`):
  a model id, or `null` to use the default. All are `null` today —
  one model for everything until a per-format difference is measured.
- `dimensions` table for known models; unknown models are probed
  once (`probe_dimensions`) and cached per run.

Resolution order: workflow input `embedding_model` → per-format
override → default. Failover: if Bedrock rejects the resolved model
(AccessDenied / Validation / NotFound — typically model access not
enabled in the console), the embedder tries the default model once
and records the model actually used. If the default is also rejected,
the document fails and the shard retries via SQS/Batch.

### 16.4 What indexing does NOT do

- No retrieval, no hybrid search, no reranking, no agents — those
  read these indexes from API-Services.
- No OCR for PNG at index time — the manifest ground-truth
  description is indexed instead.
- No multi-modal embeddings yet — text embeddings only.
