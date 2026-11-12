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

## Deployments

See `deployments/README.md`. In short: the image is built from
this folder as the Docker build context
(`docker build -f Dockerfile .`) by the
`provision-infra.yml` workflow, pushed to ECR as
`<project>-worker`, and the CloudFormation stacks in `infra/`
are deployed by the same workflow. Data generation is triggered
manually, one workflow per format, via the root
`.github/workflows/generate-<format>.yml` files.

Full documentation lives at the repo root: `README.md`,
`ARCHITECTURE.md`, `DESIGN.md`, `GITHUB_ISSUES.md`.
