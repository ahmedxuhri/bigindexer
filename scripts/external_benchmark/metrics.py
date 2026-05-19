"""Clustering similarity metrics for external benchmark.

Pairwise precision/recall/F1 and MoJoFM. All metrics operate on
{file_path: cluster_id} dictionaries over the same set of files.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Dict, Mapping


def _restrict_and_align(
    a: Mapping[str, str],
    b: Mapping[str, str],
) -> tuple[Dict[str, str], Dict[str, str]]:
    common = sorted(set(a) & set(b))
    return {k: a[k] for k in common}, {k: b[k] for k in common}


def pairwise_prf(
    predicted: Mapping[str, str],
    ground_truth: Mapping[str, str],
) -> dict:
    """Pairwise precision/recall/F1 on co-clustering decisions.

    For each pair (i, j) of files, compare same-cluster-in-predicted
    against same-cluster-in-ground-truth. TP = both same; FP = same in
    predicted but not in truth; FN = same in truth but not in predicted.
    """
    pred, truth = _restrict_and_align(predicted, ground_truth)
    files = sorted(pred)
    if len(files) < 2:
        return {"tp": 0, "fp": 0, "fn": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0, "n_items": len(files)}

    tp = fp = fn = 0
    for i, j in combinations(files, 2):
        same_pred = pred[i] == pred[j]
        same_truth = truth[i] == truth[j]
        if same_pred and same_truth:
            tp += 1
        elif same_pred and not same_truth:
            fp += 1
        elif same_truth and not same_pred:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "n_items": len(files),
    }


def mojofm(
    predicted: Mapping[str, str],
    ground_truth: Mapping[str, str],
) -> dict:
    """MoJoFM (Tzerpos & Holt) similarity score.

    mno(A,B) = sum over clusters a in A of (|a| - max overlap with any b in B)
             + (|A| - distinct best-matched b's)
    MoJoFM(A,B) = 1 - mno(A,B) / max_mno(B)
    where max_mno(B) = N - max_b |b|. Higher is better; 1.0 = exact match.
    """
    pred, truth = _restrict_and_align(predicted, ground_truth)
    if not pred:
        return {"mojofm": 0.0, "mno": 0, "max_mno": 0, "n_items": 0}

    a_clusters: dict[str, list[str]] = defaultdict(list)
    for f, c in pred.items():
        a_clusters[c].append(f)

    b_clusters: dict[str, list[str]] = defaultdict(list)
    for f, c in truth.items():
        b_clusters[c].append(f)

    n = len(pred)
    max_b_size = max(len(v) for v in b_clusters.values())
    max_mno = n - max_b_size

    moves = 0
    best_match_targets = []
    for a_id, a_files in a_clusters.items():
        overlaps = Counter(truth[f] for f in a_files)
        best_b, best_size = overlaps.most_common(1)[0]
        moves += len(a_files) - best_size
        best_match_targets.append(best_b)

    joins = len(a_clusters) - len(set(best_match_targets))
    mno = moves + joins
    score = 1.0 - (mno / max_mno) if max_mno > 0 else 1.0
    return {
        "mojofm": round(score, 4),
        "mno": mno,
        "max_mno": max_mno,
        "moves": moves,
        "joins": joins,
        "n_items": n,
        "n_pred_clusters": len(a_clusters),
        "n_truth_clusters": len(b_clusters),
    }


if __name__ == "__main__":
    truth = {f"f{i}": "A" if i < 5 else "B" for i in range(10)}
    perfect = dict(truth)
    swapped = {f"f{i}": "B" if i < 5 else "A" for i in range(10)}
    one_off = dict(truth); one_off["f0"] = "B"
    all_same = {f"f{i}": "X" for i in range(10)}

    for label, pred in [("perfect", perfect), ("swapped (label-equiv)", swapped),
                         ("one-off", one_off), ("all-same", all_same)]:
        prf = pairwise_prf(pred, truth)
        mj = mojofm(pred, truth)
        print(f"{label:25s} F1={prf['f1']:.3f}  MoJoFM={mj['mojofm']:.3f}")
