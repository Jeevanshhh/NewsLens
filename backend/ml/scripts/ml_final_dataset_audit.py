"""PHASE B/C/D - canonical final development dataset + 20-point audit + split ids.

B: Merge the DEDUPED corpus (split + cluster + hashes) with the FINAL adjudicated
   annotations, preserving pass1 / pass2 / adjudicated labels, confidence, status
   and full annotation history. ``unresolved`` records stay explicitly flagged and
   are marked ``usable_for_training = False`` (never silently treated as verified).

C: A complete read-only audit (20 checks). NO record is altered to improve any
   metric; insufficiently-represented classes are simply reported.

D: An explicit split-id manifest (train/val/test ids) + leakage re-check.

No article text is written into the audit report (ids / counts / tokens only).

Run:  python backend/ml/scripts/ml_final_dataset_audit.py
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    DATASET_AUDIT_MD,
    DATASET_ID,
    DEDUPED_JSONL,
    FALLBACK_LABEL,
    FINAL_ANNOTATIONS,
    FINAL_DATASET,
    ORIGINAL_DATASET,
    PASS2_ANNOTATIONS,
    RIGHTS_STATUS,
    SPLIT_IDS,
    TAXONOMY,
)
from ml_dedupe_split import norm_title, norm_url  # noqa: E402

LABELS = TAXONOMY + [FALLBACK_LABEL]
_token = re.compile(r"[a-z]+")


def _load_jsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def _malformed_url(u):
    if not u:
        return True
    return not re.match(r"^https?://", u.strip().lower())


def build_final():
    dedup = {r["id"]: r for r in _load_jsonl(DEDUPED_JSONL)}
    finals = {r["id"]: r for r in _load_jsonl(FINAL_ANNOTATIONS)}
    pass2 = {r["id"]: r for r in _load_jsonl(PASS2_ANNOTATIONS)}

    out = []
    for rid, base in sorted(dedup.items()):
        fin = finals.get(rid, {})
        p2 = pass2.get(rid, {})
        rec = dict(base)  # content, split, cluster, hashes, source metadata
        rec["label"] = fin.get("label", base.get("label"))
        rec["annotation_status"] = fin.get("adjudication_status", "unresolved")
        rec["annotation_confidence"] = fin.get("annotation_confidence",
                                               base.get("annotation_confidence"))
        rec["review_required"] = fin.get("review_required", True)
        rec["annotator_id"] = fin.get("annotator_id", "adjudicated_v0")
        rec["human_verified"] = False
        rec["usable_for_training"] = rec["annotation_status"] != "unresolved"
        hist = fin.get("history", {}) or {}
        rec["annotation_history"] = {
            "pass1": hist.get("pass1", {"label": base.get("label"),
                                          "conf": base.get("annotation_confidence")}),
            "pass2": hist.get("pass2", {"label": p2.get("label"),
                                          "conf": p2.get("annotation_confidence")}),
            "adjudicated": {"label": rec["label"], "status": rec["annotation_status"]},
        }
        rec["pass2_is_human"] = bool(p2.get("is_human", False))
        rec["rights_status"] = RIGHTS_STATUS
        rec["original_dataset"] = ORIGINAL_DATASET
        rec["dataset_id"] = DATASET_ID
        out.append(rec)

    with open(FINAL_DATASET, "w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out


def audit(recs):
    a = {}
    a["n_records"] = len(recs)
    a["missing_title"] = sum(1 for r in recs if not (r.get("title") or "").strip())
    a["missing_description"] = sum(1 for r in recs if not (r.get("description") or "").strip())
    a["malformed_urls"] = sum(1 for r in recs if _malformed_url(r.get("url")))

    exact_url = Counter((r.get("url") or "").lower().strip() for r in recs if r.get("url"))
    a["duplicate_exact_urls"] = sum(c - 1 for c in exact_url.values() if c > 1)
    nurl = Counter(norm_url(r.get("url") or "") for r in recs if r.get("url"))
    a["duplicate_normalized_urls"] = sum(c - 1 for c in nurl.values() if c > 1)
    dt = Counter(norm_title(r.get("title") or "") for r in recs if r.get("title"))
    a["duplicate_titles"] = sum(c - 1 for c in dt.values() if c > 1)
    td = Counter(((r.get("title") or "") + "\u0001" + (r.get("description") or "")).strip().casefold()
                 for r in recs)
    a["duplicate_title_desc"] = sum(c - 1 for c in td.values() if c > 1)

    clusters = defaultdict(list)
    for r in recs:
        clusters[r.get("duplicate_cluster_id")].append(r)
    a["unique_clusters"] = len(clusters)
    a["near_or_dup_clusters_gt1"] = sum(1 for v in clusters.values() if len(v) > 1)

    leak = sum(1 for v in clusters.values() if len({x["split"] for x in v}) > 1)
    a["cross_split_duplicate_clusters"] = leak
    a["missing_labels"] = sum(1 for r in recs if not r.get("label"))
    a["invalid_labels"] = sum(1 for r in recs if r.get("label") not in LABELS)

    dist = Counter(r["label"] for r in recs)
    present = {k: v for k, v in dist.items() if v > 0}
    a["class_distribution"] = {lab: dist.get(lab, 0) for lab in LABELS}
    a["class_imbalance_ratio"] = round(max(present.values()) / min(present.values()), 2) if present else None
    a["insufficient_classes_lt20"] = sorted(k for k, v in dist.items() if v < 20)

    src = Counter((r.get("source") or "").strip() for r in recs)
    a["n_sources"] = len(src)
    top_src, top_n = src.most_common(1)[0]
    a["top_source"] = {"name": top_src, "share": round(top_n / len(recs), 4)}

    month = Counter((r.get("published_date") or "")[:7] for r in recs)
    tm, tmn = month.most_common(1)[0]
    a["temporal_top_month"] = {"month": tm, "share": round(tmn / len(recs), 4)}

    lang = Counter(r.get("language") for r in recs)
    a["language_distribution"] = dict(lang)

    lens = [len(r.get("model_text") or "") for r in recs]
    a["model_text_char_len"] = {
        "min": min(lens), "median": int(statistics.median(lens)),
        "mean": round(statistics.mean(lens), 1), "max": max(lens),
    }

    doc_tokens = [set(_token.findall((r.get("model_text") or "").lower())) for r in recs]
    df = Counter()
    for s in doc_tokens:
        df.update(s)
    vocab = list(df)
    a["vocabulary_size"] = len(vocab)
    a["hapax_legomena"] = sum(1 for t in vocab if df[t] == 1)
    a["tokens_df_le2"] = sum(1 for t in vocab if df[t] <= 2)

    by_class_df = defaultdict(Counter)
    for r, s in zip(recs, doc_tokens):
        by_class_df[r["label"]].update(s)
    class_vocab = {}
    for lab in sorted(present):
        total_cls = len([r for r in recs if r["label"] == lab])
        scored = []
        for tok, c in by_class_df[lab].items():
            out_c = sum(by_class_df[o][tok] for o in present if o != lab)
            if c >= 2 and c > out_c:
                scored.append((c - out_c, tok))
        scored.sort(reverse=True)
        class_vocab[lab] = [t for _s, t in scored[:8]]
    a["class_specific_vocabulary"] = class_vocab

    a["potential_leakage_note"] = (
        "cluster_split_duplicate_leakage=%d; frozen-99 is SEED-derived and disjoint "
        "from this corpus (cannot be contaminated). Labels + TF-IDF share surface-text "
        "features -> optimistic-upper-bound caveat applies." % leak
    )
    return a


def split_manifest(recs):
    ids = {"train": [], "val": [], "test": []}
    train_usable = []
    for r in recs:
        ids[r["split"]].append(r["id"])
        if r["split"] == "train" and r["usable_for_training"]:
            train_usable.append(r["id"])
    return {
        "dataset_id": DATASET_ID,
        "splits": ids,
        "counts": {k: len(v) for k, v in ids.items()},
        "train_ids_usable_for_training": train_usable,
        "unresolved_ids_excluded_from_training": [
            r["id"] for r in recs if r["annotation_status"] == "unresolved"
        ],
        "note": "Split assignment reused from ml_dedupe_split (cluster-before-split). "
                "Frozen-99 untouched / disjoint.",
    }


def write_audit_md(a):
    L = ["# NewsLens Dev Dataset - Final Audit (v0.1)", "",
         f"**Records:** {a['n_records']} | **Rights:** {RIGHTS_STATUS} (UNVERIFIED) | "
         f"**Human-verified:** 0",
         "", "## Integrity checks",
         f"1. Missing title: **{a['missing_title']}**",
         f"2. Missing description: **{a['missing_description']}**",
         f"3. Malformed URLs: **{a['malformed_urls']}**",
         f"4. Duplicate exact URLs: **{a['duplicate_exact_urls']}**",
         f"5. Duplicate normalized URLs: **{a['duplicate_normalized_urls']}**",
         f"6. Duplicate titles: **{a['duplicate_titles']}**",
         f"7. Duplicate title+description: **{a['duplicate_title_desc']}**",
         f"8. Near/dup clusters >1: **{a['near_or_dup_clusters_gt1']}** "
         f"(unique clusters {a['unique_clusters']})",
         f"9. Cross-split duplicate clusters (leakage): **{a['cross_split_duplicate_clusters']}**",
         f"10. Missing labels: **{a['missing_labels']}**",
         f"11. Invalid labels: **{a['invalid_labels']}**",
         "", "## Distribution",
         f"12. Class imbalance ratio (max/min present): **{a['class_imbalance_ratio']}**",
         f"    - distribution: {a['class_distribution']}",
         f"    - insufficient (<20): {a['insufficient_classes_lt20']}",
         f"13. Source concentration: {a['n_sources']} sources, top share "
         f"**{a['top_source']['share']}** ({a['top_source']['name']})",
         f"14. Temporal concentration: top month **{a['temporal_top_month']['month']}** "
         f"= {a['temporal_top_month']['share']*100:.1f}%",
         f"15. Language distribution: {a['language_distribution']}",
         f"16. model_text length (chars): {a['model_text_char_len']}",
         f"17. Vocabulary size: **{a['vocabulary_size']}**",
         f"18. Rare tokens: hapax **{a['hapax_legomena']}**, df<=2 **{a['tokens_df_le2']}**",
         "19. Class-specific vocabulary (top discriminative tokens per class):",
    ]
    for lab, toks in a["class_specific_vocabulary"].items():
        L.append(f"    - {lab}: {', '.join(toks)}")
    L += ["", "20. Potential leakage:", f"    - {a['potential_leakage_note']}", "",
          "_No article text is included. No record was altered to improve metrics._", ""]
    with open(DATASET_AUDIT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    if not os.path.exists(DEDUPED_JSONL):
        raise SystemExit("missing deduped corpus; run ml_dedupe_split.py first")
    recs = build_final()
    a = audit(recs)
    write_audit_md(a)
    sm = split_manifest(recs)
    with open(SPLIT_IDS, "w", encoding="utf-8") as f:
        json.dump(sm, f, indent=2, ensure_ascii=False)
    print(json.dumps({"records": len(recs), "usable_for_training":
                      sum(1 for r in recs if r["usable_for_training"]),
                      "cross_split_leakage": a["cross_split_duplicate_clusters"],
                      "counts": sm["counts"],
                      "insufficient": a["insufficient_classes_lt20"],
                      "vocab": a["vocabulary_size"]}, indent=2))
    print("DONE B/C/D")


if __name__ == "__main__":
    main()
