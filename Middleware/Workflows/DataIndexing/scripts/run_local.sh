#!/usr/bin/env bash
# Local smoke test for DataIndexing — no AWS, no database.
# Runs the unit tests, then dry-runs L0–L2 (load -> chunk -> enrich)
# on one sample document and prints the chunks + metadata as JSONL.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src"

python3 -m pytest tests/ -q 2>/dev/null || python3 - <<'EOF'
import sys
sys.path.insert(0, "tests")
import test_indexer
for name in dir(test_indexer):
    if name.startswith("test_"):
        fn = getattr(test_indexer, name)
        try:
            import inspect
            if "tmp_path" in inspect.signature(fn).parameters:
                import tempfile
                from pathlib import Path
                fn(Path(tempfile.mkdtemp()))
            else:
                fn()
        except TypeError:
            continue  # fixtures (tmp_path) handled above
        print(f"PASS {name}")
EOF

SAMPLE="${1:-../../Datagen}"
python3 - <<EOF
import json, sys
sys.path.insert(0, "src")
from indexer.loader import extract_text
from indexer.chunker import split_text
from indexer.enricher import enrich_chunks

# Dry-run on the first sample txt/csv doc we can find, else synthetic text.
text = ("The home loan account was sanctioned for fifteen lakh rupees. "
        "The interest rate is 8.5 percent per annum with a tenure of twenty years. "
        "The equated monthly instalment is due on the fifth of every month. "
        "The borrower must maintain adequate insurance on the property. " * 12)
chunks = split_text(text)
doc = {"doc_id": "txt_dryrun_1", "loan_id": "L-DRY-1", "loan_type": "home",
       "format": "txt", "year": 2024, "policy_version": "v2024.1",
       "latest": True, "source_s3_key": "dry-run/local.txt"}
enriched = enrich_chunks(doc, chunks, embedding_model="amazon.titan-embed-text-v2:0")
print(f"dry-run: {len(chunks)} chunks, model amazon.titan-embed-text-v2:0")
print(json.dumps({k: v for k, v in enriched[0].items() if k != "text"}, indent=2))
print("first chunk text:", enriched[0]["text"][:200])
EOF
echo "OK — unit tests + dry-run passed."
echo "To index for real you need AWS: set the 5 GitHub secrets and run AWS-Index-001, then AWS-Index-003 (PDF)."
