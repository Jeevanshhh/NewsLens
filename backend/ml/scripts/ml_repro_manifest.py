"""Phase X - Reproducibility manifest (reproducibility_manifest_v0.1.json).

Freezes the *exact* inputs and environment that produced the development model
so a future auditor can re-run the pipeline and detect drift. Records SHA-256
hashes (never article text) of every canonical dataset / annotation / split /
config / model artifact, plus library versions, the random seed and a UTC
timestamp. Read-only: touches nothing but the report file.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ml_config as C  # noqa: E402


def _sha256(path: str):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_count(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def _entry(path: str, with_lines: bool = False):
    e = {"path": os.path.relpath(path, C.BACKEND).replace("\\", "/"),
         "exists": os.path.exists(path),
         "sha256": _sha256(path)}
    if e["exists"]:
        e["bytes"] = os.path.getsize(path)
    if with_lines:
        e["line_count"] = _line_count(path)
    return e


def main() -> int:
    # Library / runtime versions.
    versions = {"python": sys.version.split()[0]}
    try:
        import sklearn
        versions["scikit-learn"] = sklearn.__version__
    except Exception:
        versions["scikit-learn"] = "unavailable"
    try:
        import numpy
        versions["numpy"] = numpy.__version__
    except Exception:
        versions["numpy"] = "unavailable"
    try:
        import joblib
        versions["joblib"] = joblib.__version__
    except Exception:
        versions["joblib"] = "unavailable"

    # Final-model metadata (to bind the manifest to a concrete artifact).
    model_meta = {}
    if os.path.exists(C.FINAL_META):
        with open(C.FINAL_META, "r", encoding="utf-8") as fh:
            mm = json.load(fh)
        model_meta = {
            "selected_candidate": mm.get("selected_candidate"),
            "model_version": mm.get("model_version"),
            "class_list": mm.get("class_list"),
            "abstention_threshold": mm.get("abstention_threshold"),
            "training_row_count": mm.get("training_row_count"),
            "rights_status": mm.get("rights_status"),
            "production_approved": mm.get("production_approved"),
        }

    manifest = {
        "schema": "newslens_ml_reproducibility_v0.1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": C.DATASET_ID,
        "preprocessing_version": C.PREPROCESSING_VERSION,
        "model_text_builder": "app.services.processing.model_text.build_model_text",
        "random_seed": C.RANDOM_SEED,
        "taxonomy": C.TAXONOMY + [C.FALLBACK_LABEL],
        "versions": versions,
        "hashes": {
            "raw_corpus": _entry(C.RAW_JSONL, with_lines=True),
            "deduped_corpus": _entry(C.DEDUPED_JSONL, with_lines=True),
            "final_dataset": _entry(C.FINAL_DATASET, with_lines=True),
            "annotations_pass1": _entry(C.ANNOTATIONS_JSONL, with_lines=True),
            "annotations_pass2": _entry(C.PASS2_ANNOTATIONS, with_lines=True),
            "annotations_final": _entry(C.FINAL_ANNOTATIONS, with_lines=True),
            "adjudication": _entry(C.ADJUDICATION_JSONL, with_lines=True),
            "split_ids_manifest": _entry(C.SPLIT_IDS),
            "splits_manifest": _entry(C.SPLITS_MANIFEST),
            "training_config": _entry(C.TRAINING_CONFIG),
            "rights_gate": _entry(C.RIGHTS_GATE),
            "final_model": _entry(C.FINAL_MODEL),
            "final_model_meta": _entry(C.FINAL_META),
        },
        "candidate_models": {
            name: _entry(os.path.join(C.CANDIDATES_DIR, name))
            for name in sorted(os.listdir(C.CANDIDATES_DIR))
            if name.endswith(".joblib")
        } if os.path.isdir(C.CANDIDATES_DIR) else {},
        "final_model_summary": model_meta,
        "integrity_notes": [
            "Article text is intentionally NOT hashed or stored; only aggregate "
            "line counts and file digests are recorded.",
            "All artifacts under backend/ml are git-ignored; this manifest is a "
            "development provenance record, not a production release lock.",
            "Rights remain UNVERIFIED_GOOGLE_NEWS and production_approved=false; "
            "reproducibility does NOT imply production readiness.",
        ],
    }

    with open(C.REPRO_JSON, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print("wrote", C.REPRO_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
