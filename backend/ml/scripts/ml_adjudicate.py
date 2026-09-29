"""PHASE 22: Adjudication of pass-1 / pass-2 disagreements + final annotation file.

Because only TWO annotations exist, there is no majority to fall back on, so a
*documented* primary-subject adjudication policy is applied instead of silently
choosing a label. Annotation history is NEVER overwritten - pass 1 and pass 2
files remain; decisions go to a separate adjudication log + final file.

Policy (in order):
  1. agree                         -> independently_agreed
  2. one is Other, other specific with conf >= 0.60
                                    -> adjudicated (take the specific label; the
                                       fallback method under-signalled the dominant
                                       editorial subject)
  3. both specific & different      -> higher-confidence label if margin >= 0.15,
                                       else UNRESOLVED (needs human)
  4. one Other + one specific <0.60 -> UNRESOLVED (needs human)

Statuses: independently_agreed | adjudicated | unresolved. unresolved keeps the
pass-1 label but is flagged review_required (still provisional, not verified).

Run:  python backend/ml/scripts/ml_adjudicate.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import (  # noqa: E402
    ADJUDICATION_JSONL,
    ADJUDICATION_MD,
    ANNOTATIONS_JSONL,
    DATASET_ID,
    FALLBACK_LABEL,
    FINAL_ANNOTATIONS,
    PASS2_ANNOTATIONS,
    RIGHTS_STATUS,
    TAXONOMY,
)

MIN_SPECIFIC_CONF = 0.60
MIN_MARGIN = 0.15


def adjudicate(l1, c1, l2, c2):
    if l1 == l2:
        return l1, "independently_agreed", "annotators agree", round((c1 + c2) / 2, 3), False
    # one is Other
    if {l1, l2} == {FALLBACK_LABEL} or FALLBACK_LABEL in (l1, l2):
        other_label, other_conf = (l2, c2) if l1 == FALLBACK_LABEL else (l1, c1)
        if other_label != FALLBACK_LABEL and other_conf >= MIN_SPECIFIC_CONF:
            final = other_label
            return final, "adjudicated", (
                f"one method abstained to Other; the other detected a confident "
                f"dominant subject ({other_label}, conf={other_conf})"
            ), other_conf, False
        return l1, "unresolved", "Other vs low-confidence specific - needs human", c1, True
    # both specific, different
    if abs(c1 - c2) >= MIN_MARGIN:
        final, conf = (l1, c1) if c1 >= c2 else (l2, c2)
        return final, "adjudicated", (
            f"conflicting specific labels; chose higher-confidence ({final})"
        ), conf, False
    return l1, "unresolved", (
        f"conflicting specific labels with no clear margin ({l1} c{c1} vs {l2} c{c2})"
    ), c1, True


def main() -> None:
    for p in (ANNOTATIONS_JSONL, PASS2_ANNOTATIONS):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")
    p1 = {json.loads(l)["id"]: json.loads(l) for l in open(ANNOTATIONS_JSONL, encoding="utf-8")}
    p2 = {json.loads(l)["id"]: json.loads(l) for l in open(PASS2_ANNOTATIONS, encoding="utf-8")}
    ids = sorted(set(p1) & set(p2))

    final_rows, adj_rows = [], []
    status_count = Counter()
    final_class = Counter()

    for i in ids:
        a1, a2 = p1[i], p2[i]
        final, status, reason, conf, review = adjudicate(
            a1["label"], a1.get("annotation_confidence") or 0.0,
            a2["label"], a2.get("annotation_confidence") or 0.0,
        )
        status_count[status] += 1
        final_class[final] += 1
        final_rows.append({
            "id": i, "label": final,
            "adjudication_status": status,
            "annotation_confidence": conf,
            "review_required": review,
            "annotator_id": "adjudicated_v0",
            "history": {
                "pass1": {"label": a1["label"], "conf": a1.get("annotation_confidence")},
                "pass2": {"label": a2["label"], "conf": a2.get("annotation_confidence")},
            },
        })
        if status != "independently_agreed":
            adj_rows.append({
                "id": i, "original": [a1["label"], a2["label"]],
                "original_conf": [a1.get("annotation_confidence"), a2.get("annotation_confidence")],
                "final_label": final, "adjudication_status": status,
                "adjudication_reason": reason, "confidence": conf,
            })

    with open(FINAL_ANNOTATIONS, "w", encoding="utf-8") as f:
        for row in final_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(ADJUDICATION_JSONL, "w", encoding="utf-8") as f:
        for row in adj_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    n = len(ids)
    verified = status_count["independently_agreed"] + status_count["adjudicated"]
    summary = {
        "dataset_id": DATASET_ID,
        "rights_status": RIGHTS_STATUS,
        "total": n,
        "status_counts": dict(status_count),
        "independently_agreed": status_count["independently_agreed"],
        "adjudicated": status_count["adjudicated"],
        "unresolved_review_required": status_count["unresolved"],
        "automated_verified_count": verified,
        "human_verified_count": 0,
        "final_class_distribution": {c: final_class.get(c, 0) for c in TAXONOMY + [FALLBACK_LABEL]},
        "note": (
            "'automated_verified' = agreed-or-adjudicated by TWO AUTOMATED passes; it is "
            "NOT human verification. unresolved rows keep the pass-1 label, flagged for a "
            "human reviewer. Article.category was never used. Production human gate UNMET."
        ),
    }
    _write_md(summary, adj_rows)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _write_md(s, adj_rows):
    lines = [
        "# Adjudication Report (Development v0.1) - Phase 22",
        "",
        f"- **Dataset:** {s['dataset_id']} | **Rights:** {s['rights_status']}",
        f"- Total records: **{s['total']}**",
        f"- Independently agreed: **{s['independently_agreed']}**",
        f"- Adjudicated (documented policy applied): **{s['adjudicated']}**",
        f"- Unresolved / review-required: **{s['unresolved_review_required']}**",
        f"- Human-verified: **{s['human_verified_count']}** (both passes are automated)",
        "",
        "> No majority vote was used (only two annotations exist). A documented",
        "> primary-subject policy resolved disagreements; unclear cases are left",
        "> UNRESOLVED for a human, never silently guessed. Annotation history is preserved.",
        "",
        "## Final (automated) class distribution",
        "| Class | n |",
        "|---|---|",
    ]
    for c, v in s["final_class_distribution"].items():
        lines.append(f"| {c} | {v} |")
    lines += ["", "## Example adjudication decisions (record IDs only, first 25)"]
    for r in adj_rows[:25]:
        lines.append(
            f"- id {r['id']}: {r['original']} -> **{r['final_label']}** "
            f"[{r['adjudication_status']}] ({r['adjudication_reason']})"
        )
    lines += ["", "## Caveat", "- " + s["note"], ""]
    with open(ADJUDICATION_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
