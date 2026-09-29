"""PHASE 6-7: Deterministic deduplication (cluster-before-split) + stratified split.

Dedup keys (a record joins a cluster if it shares ANY key with another):
  1. exact URL (lower-cased)
  2. normalised URL (scheme/www/trailing-slash/query stripped)
  3. exact title
  4. normalised title (casefold + punctuation removed)
  5. exact title + description
  6. near-duplicate text (token Jaccard >= 0.85) on model_text

Leakage control: every member of a duplicate cluster is forced into the SAME
split (we split at CLUSTER granularity, never at record granularity).

Frozen 99 handling (documented, not silently replaced):
  The existing 99-item frozen holdout is deterministically derived from the
  SYNTHETIC SEED_CORPUS in ``news_topics_data.py`` (split_corpus(), random_state
  =42), NOT from these 396 real Google-News articles. The two sets are disjoint,
  so this development split cannot contaminate the frozen 99. The frozen 99 is
  therefore left untouched and remains a separate benchmark; this script only
  creates the development train/val/test for the new corpus.

Run:  python backend/ml/scripts/ml_dedupe_split.py
"""
from __future__ import annotations

import json
import os
import random
import re
from collections import Counter, defaultdict

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    DATASET_ID,
    FALLBACK_LABEL,
    LABELLED_JSONL,
    DEDUPED_JSONL,
    RANDOM_SEED,
    SPLITS_MANIFEST,
    TAXONOMY,
)

TRAIN, VAL, TEST = 0.75, 0.15, 0.10
NEAR_DUP_JACCARD = 0.85

_word = re.compile(r"\w+")
_punct = re.compile(r"[^0-9a-z ]+")


def norm_url(u: str) -> str:
    if not u:
        return ""
    u = u.lower().strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("?")[0].split("#")[0]
    return u.rstrip("/")


def norm_title(t: str) -> str:
    t = (t or "").casefold()
    t = _punct.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


class DSU:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main() -> None:
    if not os.path.exists(LABELLED_JSONL):
        raise SystemExit(f"missing labelled dataset: {LABELLED_JSONL} (run ml_annotate.py)")

    records = [json.loads(line) for line in open(LABELLED_JSONL, encoding="utf-8")]
    n = len(records)
    dsu = DSU(n)

    # --- exact / normalised key blocking ---
    keymaps = defaultdict(list)
    for i, r in enumerate(records):
        for key in (
            ("url", (r.get("url") or "").lower().strip()),
            ("nurl", norm_url(r.get("url") or "")),
            ("title", (r.get("title") or "").strip()),
            ("ntitle", norm_title(r.get("title") or "")),
            ("td", ((r.get("title") or "") + "\u0001" + (r.get("description") or "")).strip().casefold()),
        ):
            if key[1]:
                keymaps[key].append(i)
    dup_reason = Counter()
    for (_kind, _val), idxs in keymaps.items():
        for a in range(1, len(idxs)):
            dsu.union(idxs[0], idxs[a])
            dup_reason[_kind] += len(idxs) - 1

    # --- near-duplicate text (token Jaccard) ---
    tokensets = [set(_word.findall((r.get("model_text") or "").lower())) for r in records]
    for i in range(n):
        if not tokensets[i]:
            continue
        for j in range(i + 1, n):
            if dsu.find(i) == dsu.find(j):
                continue
            b = tokensets[j]
            if not b:
                continue
            inter = len(tokensets[i] & b)
            if inter == 0:
                continue
            union = len(tokensets[i] | b)
            if inter / union >= NEAR_DUP_JACCARD:
                dsu.union(i, j)
                dup_reason["near_dup_jaccard"] += 1

    # cluster ids
    roots = {}
    clusters = defaultdict(list)
    for i in range(n):
        root = dsu.find(i)
        if root not in roots:
            roots[root] = f"dup_{len(roots):04d}"
        cid = roots[root]
        records[i]["duplicate_cluster_id"] = cid
        clusters[cid].append(i)

    n_clusters = len(clusters)
    dup_clusters = {c: idx for c, idx in clusters.items() if len(idx) > 1}

    # --- choose a representative label per cluster (majority label) ---
    cluster_label = {}
    for cid, idx in clusters.items():
        labs = Counter(records[i].get("label") or FALLBACK_LABEL for i in idx)
        cluster_label[cid] = labs.most_common(1)[0][0]

    # --- stratified cluster-level split ---
    rng = random.Random(RANDOM_SEED)
    by_label_clusters = defaultdict(list)
    for cid in clusters:
        by_label_clusters[cluster_label[cid]].append(cid)

    assignment = {}  # cid -> split
    for lab, cids in by_label_clusters.items():
        cids = sorted(cids)
        rng.shuffle(cids)
        # count records per label to decide if stratification is possible
        rec_total = sum(len(clusters[c]) for c in cids)
        if rec_total < 3:  # cannot stratify a tiny class - all to train
            for c in cids:
                assignment[c] = "train"
            continue
        # greedy fill by record counts, keeping whole clusters intact
        targets = {"train": rec_total * TRAIN, "val": rec_total * VAL, "test": rec_total * TEST}
        filled = {"train": 0, "val": 0, "test": 0}
        order = sorted(cids, key=lambda c: -len(clusters[c]))
        for c in order:
            # put into the split furthest from its target (proportionally)
            def deficit(s):
                return targets[s] - filled[s]
            # prefer train>val>test tie-break
            best = max(("train", "val", "test"), key=lambda s: (deficit(s), s == "train", s == "val"))
            if filled["test"] >= targets["test"] and best == "test":
                best = "val" if filled["val"] < targets["val"] else "train"
            assignment[c] = best
            filled[best] += len(clusters[c])

    for i in range(n):
        records[i]["split"] = assignment[records[i]["duplicate_cluster_id"]]

    with open(DEDUPED_JSONL, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # --- manifest ---
    split_counts = Counter(r["split"] for r in records)
    split_by_label = defaultdict(lambda: Counter())
    for r in records:
        split_by_label[r["label"]][r["split"]] += 1

    leak = 0
    for cid, idx in clusters.items():
        s = {records[i]["split"] for i in idx}
        if len(s) > 1:
            leak += 1

    manifest = {
        "dataset_id": DATASET_ID,
        "method": "cluster-before-split (union-find over url/nurl/title/ntitle/title+desc + Jaccard>=0.85)",
        "random_seed": RANDOM_SEED,
        "ratios": {"train": TRAIN, "val": VAL, "test": TEST},
        "total_records": n,
        "unique_clusters": n_clusters,
        "duplicate_clusters_gt1": len(dup_clusters),
        "duplicate_records_removed_equivalent": n - n_clusters,
        "dup_reason_counts": dict(dup_reason),
        "largest_clusters": sorted(
            ((len(v), c) for c, v in clusters.items()), reverse=True
        )[:10],
        "cluster_split_leakage_violations": leak,
        "split_counts": dict(split_counts),
        "split_counts_by_label": {
            lab: dict(split_by_label[lab]) for lab in TAXONOMY + [FALLBACK_LABEL]
        },
        "frozen_99_note": (
            "Frozen 99 = SEED-corpus derived (random_state=42), disjoint from these "
            "396 real articles; left untouched, not merged into this split."
        ),
    }
    with open(SPLITS_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
