"""PHASE 21: Independent second annotation pass + blind priority-review worksheet.

INDEPENDENCE & HONESTY:
- A real *human* second annotator is NOT available for this development build.
- To exercise the agreement workflow we generate a structurally INDEPENDENT
  second pass: a classifier trained ONLY on the unrelated synthetic SEED corpus
  (news_topics_data.SEED_CORPUS). It never reads the pass-1 keyword-lexicon
  labels, so its per-record label is independent of annotator 1's output.
- This is an AUTOMATED, SINGLE-AGENT method-agreement signal. It is NOT human
  verification and does NOT satisfy the production two-human-annotator gate.
- A blind review worksheet (pass-1 labels HIDDEN) is emitted so a human reviewer
  can independently re-label the priority records.

Pass-2 output records: annotator_id, label, annotation_confidence,
annotation_status, and does NOT include the pass-1 label.

Run:  python backend/ml/scripts/ml_second_pass.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, BACKEND)

from ml_config import (  # noqa: E402
    ANNOTATIONS_JSONL,
    BLIND_REVIEW_WORKSHEET,
    FALLBACK_LABEL,
    LABELLED_JSONL,
    PASS2_ANNOTATIONS,
)

PRIORITY_CLASSES = {"Health", "Entertainment", "Sports", "Crime"}


def build_seed_predictor():
    """Independent 2nd labeler trained ONLY on the synthetic SEED corpus."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import ComplementNB
    from sklearn.pipeline import Pipeline

    from app.services.processing.news_topics_data import SEED_CORPUS

    texts = [t for t, _ in SEED_CORPUS]
    labels = [l for _, l in SEED_CORPUS]
    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2),
                                  min_df=1, stop_words="english", lowercase=True)),
        ("clf", ComplementNB(alpha=0.1)),
    ])
    pipe.fit(texts, labels)
    return pipe


def main() -> None:
    for p in (LABELLED_JSONL, ANNOTATIONS_JSONL):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p} (run ml_annotate.py first)")

    records = [json.loads(l) for l in open(LABELLED_JSONL, encoding="utf-8")]
    pass1 = {json.loads(l)["id"]: json.loads(l) for l in open(ANNOTATIONS_JSONL, encoding="utf-8")}

    model = build_seed_predictor()
    classes = list(model.classes_)

    pass2 = {}
    for r in records:
        text = r.get("model_text", "")
        feats = model.named_steps["tfidf"].transform([text])
        if feats.getnnz() == 0:
            label, conf = FALLBACK_LABEL, 0.0
        else:
            proba = model.predict_proba([text])[0]
            i = int(proba.argmax())
            label, conf = classes[i], float(proba[i])
        pass2[r["id"]] = {
            "id": r["id"],
            "annotator_id": "independent_seed_nn_v0",
            "label": label,
            "annotation_confidence": round(conf, 3),
            "annotation_status": "independent_automated_pass2",
            "method": "ComplementNB trained ONLY on synthetic SEED corpus (never saw pass-1)",
            "is_human": False,
        }

    with open(PASS2_ANNOTATIONS, "w", encoding="utf-8") as f:
        for rid in sorted(pass2):
            f.write(json.dumps(pass2[rid], ensure_ascii=False) + "\n")

    # ---- blind priority-review worksheet (pass-1 label HIDDEN) ----
    priority_ids = set()
    for r in records:
        a1 = pass1.get(r["id"], {})
        reasons = []
        if a1.get("annotation_status") == "provisional_needs_review":
            reasons.append("needs_review")
        if (a1.get("annotation_confidence") or 1.0) < 0.5:
            reasons.append("low_confidence")
        if a1.get("label") in PRIORITY_CLASSES or r.get("label") in PRIORITY_CLASSES:
            reasons.append("tiny_class")
        if a1.get("label") != pass2[r["id"]]["label"]:
            reasons.append("method_disagreement")
        if reasons:
            priority_ids.add(r["id"])
            r["_review_reason"] = ",".join(sorted(set(reasons)))

    with open(BLIND_REVIEW_WORKSHEET, "w", encoding="utf-8") as f:
        f.write("id\treview_reason\ttitle\tdescription\thuman_label_BLIND_FILL\n")
        for r in records:
            if r["id"] in priority_ids:
                title = (r.get("title") or "").replace("\t", " ")
                desc = (r.get("description") or "").replace("\t", " ").replace("\n", " ")
                f.write("\t".join([str(r["id"]), r.get("_review_reason", ""), title, desc, ""]) + "\n")

    agree_now = sum(1 for rid in pass1 if pass1[rid]["label"] == pass2[rid]["label"])
    print(json.dumps({
        "records": len(records),
        "pass2_independent_labels_written": len(pass2),
        "priority_review_records": len(priority_ids),
        "pass1_pass2_same_label": agree_now,
        "pass1_pass2_differ": len(records) - agree_now,
        "note": "pass2 is an AUTOMATED independent method, not a human; agreement is a QA signal only",
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
