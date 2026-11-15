"""F021 / S050 #80 — description overlap check for the post-run audit.

Measures the run's own txt documents (the description text, as
written by the generator) with the F013 metric from uniqueness_check.py:
wording-only word 5-gram Jaccard, digits stripped. M003 limits
(GIT_ISSUES_SEQUENCING.md): wording-only mean <= 0.15 and same
loan-type pairs with Jaccard > 0.5 <= 5%. Limits are inclusive.

All pairs are compared (O(n^2)): fine at M003 scale (200-1,000
records); 200k-record runs need MinHash/LSH (M005).
"""
import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # Datagen root
from uniqueness_check import jaccard, shingles  # noqa: E402  (F013 metric)

from audit.dedup_audit import ManifestError  # noqa: E402

WORDING_MEAN_MAX = 0.15
SAME_TYPE_HIGH = 0.5
SAME_TYPE_PCT_MAX = 5.0


def _wording_shingles(text):
    """F013 wording-only shingles, as uniqueness_check.py measures them."""
    return shingles(re.sub(r"\d+", "#", text), keep_numbers=False)


def load_descriptions(rows, base_dir):
    """(loan_type, text) for every txt row; files are relative to base_dir."""
    base_dir = Path(base_dir)
    out = []
    for row in rows:
        if row.get("format") != "txt":
            continue
        rel, loan_type = row.get("file"), row.get("loan_type")
        if not isinstance(rel, str) or not rel:
            raise ManifestError(f"txt row {row.get('doc_id')}: missing file")
        if not isinstance(loan_type, str) or not loan_type:
            raise ManifestError(f"txt row {row.get('doc_id')}: missing loan_type")
        path = base_dir / rel
        if not path.is_file():
            raise ManifestError(f"txt document not found: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ManifestError(f"{path}: not valid UTF-8") from None
        except OSError as exc:
            raise ManifestError(f"{path}: cannot read ({exc})") from None
        if not _wording_shingles(text):
            raise ManifestError(f"{path}: description too short to measure (< 5 words)")
        out.append((loan_type, text))
    if not out:
        raise ManifestError("no txt documents in the run: description overlap needs --formats with txt")
    return out


def overlap_metrics(descriptions):
    """Wording-only Jaccard over every pair of descriptions."""
    sh = [_wording_shingles(text) for _, text in descriptions]
    types = [t for t, _ in descriptions]
    total, pairs, same_pairs, same_high = 0.0, 0, 0, 0
    for i, j in itertools.combinations(range(len(sh)), 2):
        v = jaccard(sh[i], sh[j])
        total += v
        pairs += 1
        if types[i] == types[j]:
            same_pairs += 1
            if v > SAME_TYPE_HIGH:
                same_high += 1
    return {
        "descriptions": len(sh),
        "pairs": pairs,
        "mean": total / pairs if pairs else 0.0,
        "same_type_pairs": same_pairs,
        "same_type_high_pct": 100.0 * same_high / same_pairs if same_pairs else 0.0,
    }


def limit_failures(metrics):
    """One message per M003 limit the metrics exceed."""
    fails = []
    if metrics["mean"] > WORDING_MEAN_MAX:
        fails.append(f"wording-only mean {metrics['mean']:.3f} > {WORDING_MEAN_MAX}")
    if metrics["same_type_high_pct"] > SAME_TYPE_PCT_MAX:
        fails.append(f"same-type pairs >{SAME_TYPE_HIGH} {metrics['same_type_high_pct']:.2f}% "
                     f"> {SAME_TYPE_PCT_MAX:g}%")
    return fails
