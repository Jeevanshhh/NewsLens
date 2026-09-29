"""PHASE 21 (cont.): compute inter-annotator agreement between pass 1 and pass 2.

Outputs raw agreement, Cohen's kappa, per-class agreement, disagreement pairs and
changed-label count. Reports use record IDs only (NO article text is exposed).

HONESTY: pass 2 is an AUTOMATED, single-agent independent method, not a second
human. These agreement numbers are a QA/prioritisation signal; they do NOT
constitute the human two-annotator verification required for production.

Run:  python backend/ml/scripts/ml_agreement.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    AGREEMENT_JSON,
    AGREEMENT_MD,
    ANNOTATIONS_JSONL,
    FALLBACK_LABEL,
    PASS2_ANNOTATIONS,
    RIGHTS_STATUS,
    DATASET_ID,
    TAXONOMY,
)

LABELS = TAXONOMY + [FALLBACK_LABEL]


def main() -> None:
    for p in (ANNOTATIONS_JSONL, PASS2_ANNOTATIONS):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")
    p1 = {json.loads(l)["id"]: json.loads(l) for l in open(ANNOTATIONS_JSONL, encoding="utf-8")}
    p2 = {json.loads(l)["id"]: json.loads(l) for l in open(PASS2_ANNOTATIONS, encoding="utf-8")}
    ids = sorted(set(p1) & set(p2))

    a1 = [p1[i]["label"] for i in ids]
    a2 = [p2[i]["label"] for i in ids]
    n = len(ids)
    same = sum(1 for x, y in zip(a1, a2) if x == y)
    raw = same / n if n else 0.0

    # Cohen's kappa (sklearn if present, else manual).
    try:
        from sklearn.metrics import cohen_kappa_score

        kappa = float(cohen_kappa_score(a1, a2, labels=LABELS, weights=None))
    except Exception:
        po = raw
        pe = sum(
            (a1.count(l) / n) * (a2.count(l) / n) for l in set(a1) | set(a2)
        ) if n else 0.0
        kappa = (po - pe) / (1 - pe) if (1 - pe) else 0.0

    per_class = {}
    for lab in LABELS:
        idx = [k for k in range(n) if a1[k] == lab]
        if idx:
            per_class[lab] = {
                "pass1_count": len(idx),
                "agree": sum(1 for k in idx if a1[k] == a2[k]),
                "agreement_rate": round(sum(1 for k in idx if a1[k] == a2[k]) / len(idx), 3),
            }

    disagree_pairs = Counter((a1[k], a2[k]) for k in range(n) if a1[k] != a2[k])
    disagreement_ids = [ids[k] for k in range(n) if a1[k] != a2[k]]

    result = {
        "dataset_id": DATASET_ID,
        "rights_status": RIGHTS_STATUS,
        "annotator_1": p1[ids[0]].get("annotator_id"),
        "annotator_2": p2[ids[0]].get("annotator_id"),
        "annotator_2_is_human": False,
        "human_second_annotator_available": False,
        "n_compared": n,
        "raw_agreement": round(raw, 4),
        "cohen_kappa": round(kappa, 4),
        "kappa_interpretation": _kappa_interp(kappa),
        "changed_label_count": n - same,
        "per_class_agreement": per_class,
        "disagreement_pairs": [{"pass1": x, "pass2": y, "count": c}
                               for (x, y), c in disagree_pairs.most_common(20)],
        "disagreement_record_ids": disagreement_ids[:60],
        "caveat": (
            "Pass 2 is an automated, single-agent independent method (SEED-trained), "
            "NOT a human annotator. Kappa here measures METHOD disagreement to "
            "prioritise review; it is not human verification and does not satisfy the "
            "production two-human-annotator gate."
        ),
    }
    with open(AGREEMENT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    _write_md(result)
    print(json.dumps({k: result[k] for k in
                      ("n_compared", "raw_agreement", "cohen_kappa", "kappa_interpretation",
                       "changed_label_count")}, indent=2))


def _kappa_interp(k):
    if k <= 0:
        return "no agreement / slight"
    if k < 0.21:
        return "slight"
    if k < 0.41:
        return "fair"
    if k < 0.61:
        return "moderate"
    if k < 0.81:
        return "substantial"
    return "almost perfect"


def _write_md(r):
    lines = [
        "# Annotation Agreement (Development v0.1) - Phase 21",
        "",
        f"- **Dataset:** {r['dataset_id']} | **Rights:** {r['rights_status']}",
        f"- **Annotator 1:** {r['annotator_1']} (rule-assisted single annotator, provisional)",
        f"- **Annotator 2:** {r['annotator_2']} - **AUTOMATED, independent method, NOT a human**",
        f"- **Human second annotator available:** {r['human_second_annotator_available']}",
        "",
        "> **This does NOT constitute human verification.** It measures method-level",
        "> disagreement to prioritise review. The production two-human-annotator gate",
        "> remains UNMET.",
        "",
        "## Headline",
        f"- Records compared: **{r['n_compared']}**",
        f"- Raw agreement: **{r['raw_agreement']:.3f}**",
        f"- Cohen's kappa: **{r['cohen_kappa']:.3f}** ({r['kappa_interpretation']})",
        f"- Changed-label (disagreement) count: **{r['changed_label_count']}**",
        "",
        "## Per-class agreement (pass-1 label -> pass-2 match rate)",
        "| Class | pass1 n | agreed | rate |",
        "|---|---|---|---|",
    ]
    for lab in TAXONOMY + [FALLBACK_LABEL]:
        pc = r["per_class_agreement"].get(lab)
        if pc:
            lines.append(f"| {lab} | {pc['pass1_count']} | {pc['agree']} | {pc['agreement_rate']:.2f} |")
    lines += ["", "## Top disagreement pairs (pass1 -> pass2)"]
    for d in r["disagreement_pairs"][:15]:
        lines.append(f"- {d['pass1']} -> {d['pass2']}: {d['count']}")
    lines += ["", "## Priority review",
              "- A blind worksheet (pass-1 labels hidden) lists records needing human re-label:",
              "  `ml/datasets/development/blind_review_worksheet.tsv` (gitignored, article text only there).",
              f"- Disagreement record IDs (first {len(r['disagreement_record_ids'])}): "
              + ", ".join(str(i) for i in r["disagreement_record_ids"][:40]) + " ...",
              "", "## Caveat", "- " + r["caveat"], ""]
    with open(AGREEMENT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
