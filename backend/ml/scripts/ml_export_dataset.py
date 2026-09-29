"""PHASE 1-2: Read-only export of the local NewsLens corpus into a canonical
DEVELOPMENT dataset (RIGHTS UNVERIFIED) + an annotation worksheet.

- Opens the SQLite DB strictly READ-ONLY (mode=ro). SELECT only. No mutation.
- Does NOT modify Article.category or the production DB/schema.
- Emits a versioned canonical JSONL where every record carries ML fields,
  provenance, dataset/rights metadata and empty annotation slots to be filled.
- Emits a human annotation worksheet (id + current category HINT + title +
  description) so each L1 label can be assigned and manually verified.
- Prints an inventory reconciliation against the earlier read-only audit.

Run:  python backend/ml/scripts/ml_export_dataset.py
Outputs (all gitignored - article text must never reach Git):
  backend/ml/datasets/development/corpus_raw_v0.1.jsonl
  backend/ml/datasets/development/annotation_worksheet.tsv
  backend/ml/datasets/development/manifest.json
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", ".."))
DB_PATH = os.path.join(BACKEND, "newslens.db")
OUT_DIR = os.path.join(BACKEND, "ml", "datasets", "development")
os.makedirs(OUT_DIR, exist_ok=True)

# Import the SHARED preprocessing so dataset MODEL_TEXT == inference MODEL_TEXT.
import sys
sys.path.insert(0, BACKEND)
from app.services.processing.model_text import build_model_text  # noqa: E402

DATASET_ID = "newslens_topic_dev_v0.1"
ORIGINAL_DATASET = "newslens_google_news_local_corpus"
RIGHTS_STATUS = "UNVERIFIED_GOOGLE_NEWS"

TAXONOMY = [
    "World", "Politics", "Business", "Technology", "Sports", "Health",
    "Science", "Entertainment", "Climate", "Crime", "Education",
]


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> None:
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"DB not found: {DB_PATH}")
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        "SELECT id, title, description, url, source, provider, published_at, "
        "published_date, language, country, category, created_at FROM articles ORDER BY id"
    )
    rows = cur.fetchall()
    con.close()

    records = []
    for r in rows:
        model_text = build_model_text(r["title"], r["description"])
        norm_text = model_text.lower().strip()
        rec = {
            # ML
            "id": r["id"],
            "title": r["title"] or "",
            "description": r["description"] or "",
            "model_text": model_text,
            # provenance
            "source": r["source"],
            "provider": r["provider"],
            "url": r["url"],
            "published_date": r["published_date"],
            "published_at_raw": r["published_at"],
            "collected_date": r["created_at"],
            "language": r["language"],
            "country": r["country"],
            # dataset / rights
            "dataset_id": DATASET_ID,
            "original_dataset": ORIGINAL_DATASET,
            "license": None,
            "license_url": None,
            "rights_status": RIGHTS_STATUS,
            # annotation (to be filled in Phase 4)
            "label": None,
            "annotation_status": "pending",
            "annotator_id": None,
            "annotation_confidence": None,
            "current_category_hint": r["category"],  # HINT ONLY, not trusted truth
            # QA
            "duplicate_cluster_id": None,
            "content_hash": _sha(model_text),
            "normalized_text_hash": _sha(norm_text),
            "quality_flag": "ok" if (r["title"] or "").strip() else "missing_title",
            "exclusion_reason": None,
            "split": None,
        }
        records.append(rec)

    jsonl_path = os.path.join(OUT_DIR, "corpus_raw_v0.1.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # annotation worksheet (id | hint | title | description) - manual pass input
    ws_path = os.path.join(OUT_DIR, "annotation_worksheet.tsv")
    with open(ws_path, "w", encoding="utf-8") as f:
        f.write("id\tcurrent_hint\ttitle\tdescription\n")
        for rec in records:
            f.write("\t".join([
                str(rec["id"]),
                (rec["current_category_hint"] or "").replace("\t", " "),
                (rec["title"] or "").replace("\t", " "),
                (rec["description"] or "").replace("\t", " ").replace("\n", " "),
            ]) + "\n")

    # ---- inventory reconciliation (Phase 1 verification) ----
    n = len(records)
    has_title = sum(1 for x in records if (x["title"] or "").strip())
    has_desc = sum(1 for x in records if (x["description"] or "").strip())
    has_both = sum(1 for x in records if (x["title"] or "").strip() and (x["description"] or "").strip())
    langs = Counter((x["language"] or "NULL") for x in records)
    srcs = Counter((x["source"] or "NULL") for x in records)
    provs = Counter((x["provider"] or "NULL") for x in records)
    hints = Counter((x["current_category_hint"] or "NULL") for x in records)
    norm_hashes = Counter(x["normalized_text_hash"] for x in records)
    content_hashes = Counter(x["content_hash"] for x in records)
    urls = Counter((x["url"] or "").lower() for x in records)
    dup_norm = sum(c - 1 for c in norm_hashes.values() if c > 1)
    dup_content = sum(c - 1 for c in content_hashes.values() if c > 1)
    dup_url = sum(c - 1 for c in urls.values() if c > 1)

    inv = {
        "dataset_id": DATASET_ID,
        "rights_status": RIGHTS_STATUS,
        "total_records": n,
        "with_title": has_title,
        "with_description": has_desc,
        "with_title_and_description": has_both,
        "language_counts": dict(langs),
        "distinct_sources": len([k for k in srcs if k != "NULL"]),
        "provider_counts": dict(provs),
        "current_category_hint_counts": dict(hints),
        "duplicate_exact_url": dup_url,
        "duplicate_normalized_text": dup_norm,
        "duplicate_content_modeltext": dup_content,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(inv, f, indent=2, ensure_ascii=False)

    print(json.dumps(inv, indent=2, ensure_ascii=False))
    print("\nWROTE:")
    print(jsonl_path)
    print(ws_path)


if __name__ == "__main__":
    main()
