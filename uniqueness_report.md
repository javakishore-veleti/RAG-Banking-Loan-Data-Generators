# Description uniqueness — before / after

Measured on 200 descriptions, seed 7, metric = Jaccard similarity on word
5-gram shingles. 19,900 pairs.

## Method

- **With numbers:** shingles include amounts, rates, EMI — facts differ.
- **Without numbers:** digits stripped, so only wording/template overlap
  is measured. This is the honest number: two descriptions that differ
  only in numbers score near 1.0 here.
- Same loan-type pairs are reported separately, because two home loans
  will always share more wording than a home loan and a gold loan.

## Results

| Metric | v1 (one template per topic) | v2 (4 paraphrases + 3 layouts + reject loop) |
|---|---|---|
| Wording-only, mean (all pairs) | 0.246 | **0.128** |
| Wording-only, median | 0.197 | **0.107** |
| Wording-only, p90 | 0.403 | **0.201** |
| Wording-only, max | 0.882 | **0.701** |
| Wording-only, % pairs > 0.5 | 4.1% | **0.2%** |
| Wording-only, same loan-type mean | 0.333 | **0.167** |
| Wording-only, same loan-type % > 0.5 | 25.0% | **1.5%** |
| With numbers, mean | 0.099 | **0.074** |
| With numbers, % pairs > 0.5 | 0.0% | **0.0%** |

## What changed in v2

1. Four paraphrase variants per answer topic, chosen per record.
2. Three layouts (standard, question-first, status-first) and varied
   field labels (`Amount` / `Sanctioned amount`, `EMI` / `Monthly instalment`, …).
3. One contextual sentence per record, from channel / purpose / status.
4. Generate → measure → reject loop in the generator CLI:
   `--max-overlap 0.65` (default). A description whose wording-only
   5-gram Jaccard vs already-kept descriptions exceeds 0.65 is
   regenerated with a different variant/layout, up to 5 attempts.
   In the 200-record run, 3 descriptions were rejected/regenerated.

## Interpretation

- Without uniqueness enforcement, 1 in 4 same-type description pairs
  shared over half their 5-grams. For RAG retrieval that is near-duplicate
  noise: the retriever cannot tell which loan a question is about.
- After v2, that falls to 1.5% of same-type pairs. Mean wording overlap
  halved, from 0.246 to 0.128.
- The remaining overlap is mostly unavoidable domain vocabulary
  (interest rate, EMI, tenure, loan type). 100% unique text is not
  achievable — or desirable — in a single domain.
- The checker is `uniqueness_check.py`. Run it before scaling:
  `python3 uniqueness_check.py --count 200 --seed 7`

## Limit

This check is wording-only (5-gram Jaccard). It does not measure
embedding cosine similarity. At 1M scale, use MinHash/LSH in the Batch
worker (the DynamoDB hash check in the AWS repo) instead of pairwise
comparison, which does not scale.
