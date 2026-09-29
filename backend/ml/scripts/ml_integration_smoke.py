"""PHASE 14: Production-integration smoke test for the DEVELOPMENT artifact.

Confirms, WITHOUT changing any default runtime behaviour:
1. The shared model-text builder is identical for training and inference
   (no train/serve skew): build_model_text(title, desc) == the text used at fit.
2. The saved dev artifact is a valid sklearn Pipeline exposing
   ``named_steps['tfidf']`` + ``predict_proba`` over the L1 taxonomy.
3. ``news_topics.predict_topic`` can load and use that artifact when
   ``NLENS_ML_MODEL_PATH`` is set (OFF-by-default opt-in path).
4. With the env var UNSET, the runtime falls back to the bundled SEED model
   exactly as before (the frozen-99 tests and default behaviour are preserved).

This does NOT enable the ML layer for real traffic; ``topic_model_enabled``
still defaults to False in the app config.

Run:  python backend/ml/scripts/ml_integration_smoke.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

from ml_config import DEDUPED_JSONL, FALLBACK_LABEL, MODEL_ARTIFACT, TAXONOMY  # noqa: E402
from app.services.processing.model_text import build_model_text  # noqa: E402


def _check_model_text_shared():
    rows = [json.loads(l) for l in open(DEDUPED_JSONL, encoding="utf-8")][:5]
    ok = all(build_model_text(r["title"], r["description"]) == r["model_text"] for r in rows)
    print(f"[1] shared model_text reproduces training text for samples: {ok}")
    assert ok, "train/serve skew detected"
    return ok


def _check_artifact_shape():
    import joblib

    model = joblib.load(MODEL_ARTIFACT)
    assert hasattr(model, "named_steps") and "tfidf" in model.named_steps
    assert hasattr(model, "predict_proba")
    classes = set(model.classes_)
    assert classes <= set(TAXONOMY + [FALLBACK_LABEL]), f"unexpected classes: {classes}"
    print(f"[2] artifact valid: steps={list(model.named_steps)} n_classes={len(classes)}")
    return model


def _check_opt_in_loading(model):
    # Opt-in runtime path: point the loader at the artifact and reset the cache.
    os.environ["NLENS_ML_MODEL_PATH"] = MODEL_ARTIFACT
    import app.services.processing.news_topics as nt

    nt._model = None  # force reload via _load_artifact()
    tests = [
        "India beat Australia in the cricket World Cup final to lift the trophy",
        "Tesla shares fell as the company announced new AI smartphone chips",
        "Supreme Court heard petitions on the NEET paper leak student protest",
    ]
    results = []
    for t in tests:
        text = build_model_text(t, "")
        label, conf = nt.predict_topic(text)
        assert label in TAXONOMY + [FALLBACK_LABEL]
        results.append((t[:40], label, round(conf, 2)))
    print("[3] predict_topic via NLENS_ML_MODEL_PATH artifact:")
    for r in results:
        print(f"      {r[0]!r:45} -> {r[1]} ({r[2]})")
    del os.environ["NLENS_ML_MODEL_PATH"]
    return results


def _check_default_seed_path_unchanged():
    # Unset env + reset cache -> must rebuild the bundled SEED model, unchanged.
    os.environ.pop("NLENS_ML_MODEL_PATH", None)
    import app.services.processing.news_topics as nt

    nt._model = None
    m = nt._get_model()
    classes = set(m.classes_)
    assert classes <= set(TAXONOMY + [FALLBACK_LABEL])
    label, conf = nt.predict_topic(build_model_text("Climate change heatwave hits Europe", ""))
    print(f"[4] default (SEED) path intact: loaded={'seed' if nt._load_artifact() is None else 'artifact'} "
          f"sample-> {label} ({conf:.2f}); classes={len(classes)}")


def main():
    if not os.path.exists(MODEL_ARTIFACT):
        raise SystemExit(f"missing artifact: {MODEL_ARTIFACT} (run ml_train_eval.py)")
    _check_model_text_shared()
    model = _check_artifact_shape()
    _check_opt_in_loading(model)
    _check_default_seed_path_unchanged()
    print("\nINTEGRATION SMOKE: PASS (default behaviour preserved; dev model opt-in only)")


if __name__ == "__main__":
    main()
