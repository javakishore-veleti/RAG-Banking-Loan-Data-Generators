#!/usr/bin/env python3
"""Measure description uniqueness / overlap for the RAG corpus generator.

Usage:
  python3 uniqueness_check.py --count 200 --seed 7
  python3 uniqueness_check.py --count 200 --seed 7 --generator src/generator/generator.py

Metric: Jaccard similarity on word 5-gram shingles.
  - with numbers: shingles include the loan numbers (amount, rate, EMI)
  - without numbers: digits stripped, so only wording/template overlap is measured.
    This is the honest number for template overlap: if two descriptions
    differ only in numbers, their no-numbers Jaccard will be near 1.0.

Report: mean / median / p90 / max Jaccard, and % of pairs above 0.5 and 0.8.
A useful corpus for RAG should have most pairs well below 0.5 on the
no-numbers metric. Above 0.8 means near-duplicate descriptions.
"""
import argparse
import itertools
import random
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "rag-corpus-aws" / "src"))


def shingles(text, n=5, keep_numbers=True):
    pattern = r"[a-z0-9]+" if keep_numbers else r"[a-z]+"
    words = re.findall(pattern, text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--generator", default=None,
                    help="path to generator.py; default: rag-corpus-aws/src/generator/generator.py")
    args = ap.parse_args()

    gen_path = Path(args.generator) if args.generator else \
        Path(__file__).resolve().parent / "rag-corpus-aws" / "src" / "generator" / "generator.py"
    sys.path.insert(0, str(gen_path.parent.parent))
    from generator.generator import lines_for, make_record

    rng = random.Random(args.seed)
    texts, texts_nonum = [], []
    types = []
    for i in range(args.count):
        rec = make_record(rng, i)
        t = "\n".join(lines_for(rec))
        texts.append(t)
        texts_nonum.append(re.sub(r"\d+", "#", t))
        types.append(rec["loan_type"])

    def report(name, arr):
        vals = []
        same_type_vals = []
        for (i, a), (j, b) in itertools.combinations(enumerate(arr), 2):
            v = jaccard(a, b)
            vals.append(v)
            if types[i] == types[j]:
                same_type_vals.append(v)
        def pct(v, thr):
            return 100.0 * sum(1 for x in v if x > thr) / len(v) if v else 0.0
        print(f"\n{name} — {len(vals)} pairs")
        print(f"  mean={statistics.mean(vals):.3f}  median={statistics.median(vals):.3f}  "
              f"p90={sorted(vals)[int(0.9 * len(vals))]:.3f}  max={max(vals):.3f}")
        print(f"  % pairs >0.5: {pct(vals, 0.5):.1f}%   >0.8: {pct(vals, 0.8):.1f}%")
        if same_type_vals:
            print(f"  same loan-type only: mean={statistics.mean(same_type_vals):.3f}  "
                  f">0.5: {pct(same_type_vals, 0.5):.1f}%   >0.8: {pct(same_type_vals, 0.8):.1f}%")
        return vals

    print(f"Uniqueness check: {args.count} descriptions, seed={args.seed}, generator={gen_path}")
    report("WITH numbers (facts differ)", [shingles(t, keep_numbers=True) for t in texts])
    report("WITHOUT numbers (wording only — template overlap)", [shingles(t, keep_numbers=False) for t in texts_nonum])


if __name__ == "__main__":
    main()
