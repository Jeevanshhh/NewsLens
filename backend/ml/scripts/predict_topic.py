"""NewsLens Topic Classifier - DEVELOPMENT command-line demo (Phase T).

A thin, self-contained CLI around the *development* model artifact produced by
``ml_train_predict.py`` (``topic_model_dev_final_v0.1.joblib``). It exists to
demonstrate that a saved dev artifact can be loaded and used to classify a
headline exactly the way the runtime would - WITHOUT touching the database,
without training, and WITHOUT exposing any article/training text.

IMPORTANT SCOPE / HONESTY CAVEATS
---------------------------------
* This is a DEVELOPMENT CANDIDATE, not a production model. Labels are automated
  (single-annotator) and publisher content rights are UNVERIFIED, so the model
  must never be shipped to production on the strength of this demo.
* Predictions use the SHARED ``build_model_text`` preprocessing (same function
  used at training time) so train/serve skew cannot be reintroduced here.
* Abstention: if the top class probability is below the model's tuned
  abstention threshold (recorded in the ``.meta.json``), the prediction is
  reported as ABSTAINED and falls back to ``Other``.

USAGE
-----
    python predict_topic.py "Senators debate new immigration bill"
    python predict_topic.py --title "Kickers settle penalty shootout" \
                            --description "Local club wins regional cup final"
    python predict_topic.py --json "Central bank raises interest rates"
    python predict_topic.py --demo            # run a few built-in examples

The output shows the predicted L1 topic, the confidence, whether the model
abstained, and the model version. No training data is ever printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

# --- paths -----------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ml_config as C  # noqa: E402  (adds shared artifact paths)

BACKEND = C.BACKEND
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Shared train/inference preprocessing - the single source of truth.
from app.services.processing.model_text import build_model_text  # noqa: E402


def load_model():
    """Load the saved development pipeline + metadata. Refuses if absent."""
    if not os.path.exists(C.FINAL_MODEL):
        raise SystemExit(
            f"Development model artifact not found:\n  {C.FINAL_MODEL}\n"
            "Run ml_train_predict.py first to produce it."
        )
    import joblib

    model = joblib.load(C.FINAL_MODEL)
    meta: dict = {}
    if os.path.exists(C.FINAL_META):
        with open(C.FINAL_META, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
    return model, meta


def classify(model, meta, title: str, description: Optional[str]) -> dict:
    """Return a prediction dict for one article (title [+ description])."""
    text = build_model_text(title, description)
    threshold = float(meta.get("abstention_threshold", 0.30))
    classes = list(getattr(model, "classes_", []))

    result = {
        "input_title": title,
        "input_description": description or "",
        "model_text": text,
        "predicted_topic": "Other",
        "confidence": 0.0,
        "abstained": True,
        "threshold": threshold,
        "model_version": meta.get("model_version", "unknown"),
        "designation": meta.get("designation", "DEVELOPMENT CANDIDATE"),
    }

    if not text:
        result["reason"] = "empty_input"
        return result

    # Out-of-vocabulary guard (mirrors news_topics.predict_topic): an all-zero
    # transformed row means the model has never seen any of these terms.
    features = model.named_steps["tfidf"].transform([text])
    if features.getnnz() == 0:
        result["reason"] = "no_known_features (out-of-vocabulary)"
        return result

    proba = model.predict_proba([text])[0]
    idx = int(proba.argmax())
    conf = float(proba[idx])
    pred = classes[idx] if idx < len(classes) else "Other"

    result["confidence"] = round(conf, 4)
    result["predicted_topic"] = pred
    if conf < threshold:
        result["abstained"] = True
        result["reason"] = f"below_threshold ({conf:.3f} < {threshold:.3f})"
        result["predicted_topic"] = "Other"
    else:
        result["abstained"] = False
        result["reason"] = "confident"
    return result


_DEMO = [
    ("City council approves funding for new public school library", None),
    ("Stocks rally as technology earnings beat expectations", None),
    ("National team clinches semifinal spot in penalty shootout", None),
    ("Researchers announce breakthrough in renewable battery storage", None),
    ("qwer zxcv blorp fnord", None),  # out-of-vocabulary -> abstain
]


def _print_human(r: dict) -> None:
    print("-" * 68)
    print(f"Title       : {r['input_title']}")
    if r["input_description"]:
        print(f"Description : {r['input_description']}")
    flag = "ABSTAINED" if r["abstained"] else "PREDICTED"
    print(f"Topic       : {r['predicted_topic']}  "
          f"(confidence={r['confidence']:.3f}, threshold={r['threshold']:.2f}) "
          f"[{flag}]")
    print(f"Reason      : {r.get('reason', '')}")
    print(f"Model       : {r['model_version']} - {r['designation']}")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Classify a news headline with the NewsLens DEVELOPMENT model."
    )
    ap.add_argument("title_pos", nargs="?", help="Article title (positional).")
    ap.add_argument("--title", dest="title", help="Article title.")
    ap.add_argument("--description", dest="description", default=None,
                    help="Optional article description / summary.")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="Emit machine-readable JSON instead of human text.")
    ap.add_argument("--demo", action="store_true",
                    help="Run a few built-in example headlines.")
    args = ap.parse_args(argv)

    model, meta = load_model()

    if args.demo:
        out = []
        for t, d in _DEMO:
            r = classify(model, meta, t, d)
            out.append(r)
            if not args.as_json:
                _print_human(r)
        if args.as_json:
            print(json.dumps(out, indent=2))
        print("-" * 68)
        print("NOTE: DEVELOPMENT candidate only - automated labels, rights "
              "unverified, not for production use.")
        return 0

    title = args.title or args.title_pos
    if not title:
        ap.error("Provide a TITLE argument or --title (or use --demo).")

    r = classify(model, meta, title, args.description)
    if args.as_json:
        print(json.dumps(r, indent=2))
    else:
        _print_human(r)
        print("-" * 68)
        print("NOTE: DEVELOPMENT candidate only - automated labels, rights "
              "unverified, not for production use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
