#!/usr/bin/env bash
set -euo pipefail
# Local run, same code path as the Batch worker (minus SQS/S3/DynamoDB).
# Usage: ./scripts/run_local.sh [count] [out]
COUNT="${1:-10}"
OUT="${2:-./corpus}"
python3 src/generator/generator.py --count "$COUNT" --out "$OUT" --seed 7
echo "Wrote $COUNT records x 6 formats to $OUT"
