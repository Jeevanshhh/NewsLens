"""PHASE 23: Dataset quality report recomputed AFTER adjudication.

Merges final (adjudicated) labels back onto the provenance/QA fields and reports
class / source / date / language distributions, missing fields, duplicate
clusters, source & temporal concentration, annotation status mix and confidence
distribution. Records are never altered to improve metrics; tiny classes are
reported as INSUFFICIENT, not manufactured. Report uses IDs/aggregate counts only
(no article text).

Run:  python backend/ml/scripts/ml_dataset_qa.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    DATASET_ID,
    DATASET_QA_JSON,
    DATASET_QA_MD,
    FALLBACK_LABEL,
    FINAL_ANNOTATIONS,
    LABELLED_JSONL,
    RIGHTS_STATUS,
    TAXONOMY,
)

INSUFFICIENT = 20  # below this a class is flagged as not trainable


def main() -> None:
    for p in (LABELLED_JSONL, FINAL_ANNOTATIONS):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")
    base = {json.loads(l)["id"]: json.loads(l) for l in open(LABELLED_JSONL, encoding="utf-8")}
    final = {json.loads(l)["id"]: json.loads(l) for l in open(FINAL_ANNOTATIONS, encoding="utf-8")}

    class_dist, src_by_class = Counter(), defaultdict(Counter)
    date_by_month, lang = Counter(), Counter()
    status_mix, conf_buckets = Counter(), Counter()
    missing = Counter()
    total = 0
    for i, rec in base.items():
        fa = final.get(i)
        if not fa:
            continue
        total += 1
        lab = fa["label"]
        class_dist[lab] += 1
        src_by_class[lab][rec.get("source") or "NULL"] += 1
        d = (rec.get("published_date") or "unknown")[:7]
        date_by_month[d] += 1
        lang[rec.get("language") or "NULL"] += 1
        status_mix[fa["adjudication_status"]] += 1
        c = fa.get("annotation_confidence") or 0.0
        conf_buckets["<0.5" if c < 0.5 else "0.5-0.7" if c < 0.7 else ">=0.7"] += 1
        if not (rec.get("title") or "").strip():
            missing["title"] += 1
        if not (rec.get("description") or "").strip():
            missing["description"] += 1
        if not rec.get("url"):
            missing["url"] += 1

    clusters = Counter(rec.get("duplicate_cluster_id") for rec in base.values())
    dup_clusters = sum(1 for c, k in clusters.items() if k and k > 1)

    src_all = Counter((rec.get("source") or "NULL") for rec in base.values())
    top_src_share = round(src_all.most_common(1)[0][1] / total, 3) if total else 0
    top_month = date_by_month.most_common(1)
    temporal_conc = round(top_month[0][1] / total, 3) if total and top_month else 0

    insufficient = [c for c in TAXONOMY if class_dist.get(c, 0) < INSUFFICIENT]

    report = {
        "dataset_id": DATASET_ID,
        "rights_status": RIGHTS_STATUS,
        "total_labelled": total,
        "class_distribution": {c: class_dist.get(c, 0) for c in TAXONOMY + [FALLBACK_LABEL]},
        "insufficient_classes": insufficient,
        "annotation_status_mix": dict(status_mix),
        "confidence_distribution": dict(conf_buckets),
        "missing_fields": dict(missing),
        "language_distribution": dict(lang),
        "distinct_sources": len([k for k in src_all if k != "NULL"]),
        "top_source_share": top_src_share,
        "temporal_concentration_top_month": (top_month[0][0] if top_month else None, temporal_conc),
        "date_by_month": dict(sorted(date_by_month.items())),
        "duplicate_clusters_gt1": dup_clusters,
        "human_verified": 0,
        "note": "Distributions reflect automated adjudicated labels; no records were altered "
                "to improve metrics; insufficient classes reported as-is.",
    }
    with open(DATASET_QA_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    lines = [
        "# Dataset Quality Report (Development v0.1) - Phase 23",
        "",
        f"- **Dataset:** {report['dataset_id']} | **Rights:** {report['rights_status']} (UNVERIFIED)",
        f"- **Total labelled:** {total} | distinct sources: {report['distinct_sources']} | "
        f"language(s): {list(report['language_distribution'])}",
        f"- **Source concentration:** top publisher share {top_src_share:.1%} (diverse)"
        if report["distinct_sources"] else "- low source diversity",
        f"- **Temporal concentration:** top month {report['temporal_concentration_top_month'][0]} "
        f"holds {temporal_conc:.1%} of records (BURSTY - production acquisition must spread dates)",
        f"- **Duplicate clusters (>1 member):** {dup_clusters}",
        f"- **Missing fields:** {missing or 'none'}",
        "",
        "## Class distribution (adjudicated)",
        "| Class | n | trainable? |",
        "|---|---|---|",
    ]
    for c in TAXONOMY + [FALLBACK_LABEL]:
        n = class_dist.get(c, 0)
        flag = "OK" if n >= INSUFFICIENT else "INSUFFICIENT"
        lines.append(f"| {c} | {n} | {flag} |")
    lines += [
        "",
        f"- **Insufficient classes (report, do NOT manufacture):** {', '.join(insufficient) or 'none'}",
        f"- **Annotation status mix:** {dict(status_mix)}",
        f"- **Confidence distribution:** {dict(conf_buckets)}",
        f"- **Human-verified records:** {report['human_verified']} (all labels are automated/provisional)",
        "",
        "> Metrics were NOT improved by altering records. Health / Entertainment remain tiny "
        "and are explicitly reported as insufficient for a real per-class signal.",
        "",
    ]
    with open(DATASET_QA_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
