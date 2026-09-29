"""PHASE 24: Machine-readable RIGHTS GATE.

Encodes the verified rights status for every considered source and a hard gate
that downstream production phases (25-30) must check before doing anything.

Current verified findings (from the earlier rights investigation):
- google_news (the 396 dev articles)  -> RIGHTS_UNVERIFIED, NOT_APPROVED
- GNews API                           -> anti-corpus + destroy-on-termination -> NOT_APPROVED
- NewsData.io                         -> disclaims content authorisation       -> NOT_APPROVED
- (none)                              -> approved production source

A source is APPROVED only if ALL required rights are explicitly granted by the
license/terms (verified, with an agreement reference). Nothing meets this yet, so
gate.approved_source = null and Phases 25-30 MUST NOT run.

Run:  python backend/ml/scripts/ml_rights_gate.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ml_config import RIGHTS_GATE, DATASET_ID  # noqa: E402

REQUIRED_RIGHTS = [
    "storage_rights", "ml_training_rights", "commercial_use_rights",
    "model_retention_rights", "derived_dataset_rights", "redistribution_rights",
]


def _record(**kw):
    base = {
        "rights_status": "UNVERIFIED",
        "storage_rights": False,
        "ml_training_rights": False,
        "commercial_use_rights": False,
        "model_retention_rights": False,
        "derived_dataset_rights": False,
        "redistribution_rights": False,
        "attribution_requirement": "UNKNOWN",
        "source_specific_restrictions": "",
        "agreement_reference": None,
        "approval": "NOT_APPROVED",
        "blocking_reason": "",
    }
    base.update(kw)
    base["satisfies_required_rights"] = all(base[r] for r in REQUIRED_RIGHTS)
    base["approval"] = "APPROVED" if base["satisfies_required_rights"] and base["agreement_reference"] else "NOT_APPROVED"
    return base


def main() -> None:
    sources = {
        "newslens_google_news_local_corpus (dev 396)": _record(
            rights_status="RIGHTS_UNVERIFIED",
            source_specific_restrictions=(
                "Collected via Google News; publisher owns underlying content; "
                "Google does not licence publisher content for ML training."
            ),
            blocking_reason="Publisher/ML-training rights never established; corpus is "
                            "development/experimental only. Do not publish/commit/redistribute.",
        ),
        "GNews API": _record(
            rights_status="TERMS_ADVERSE",
            storage_rights=True,  # limited caching permitted
            source_specific_restrictions=(
                "ToS prohibits systematically downloading/storing to build a database; "
                "requires destroying downloaded material on termination."
            ),
            blocking_reason="Anti-corpus clause + destroy-on-termination forbid a retained "
                            "training corpus. NOT usable for a production corpus.",
        ),
        "NewsData.io": _record(
            rights_status="LEGAL_REVIEW_REQUIRED",
            storage_rights=True,
            ml_training_rights=False,
            source_specific_restrictions=(
                "Provider states it does not have the right to authorise use of third-party "
                "content; derived-data/sublicense use is 'at your own risk'."
            ),
            blocking_reason="No explicit ML-training / commercial / redistribution grant; "
                            "requires written publisher/legal clearance before any collection.",
        ),
    }

    approved = [k for k, v in sources.items() if v["approval"] == "APPROVED"]

    gate = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "development_dataset_id": DATASET_ID,
        "development_rights_status": "RIGHTS_UNVERIFIED",
        "required_rights": REQUIRED_RIGHTS,
        "sources": sources,
        "approved_sources": approved,
        "gate": {
            "rights_approved": bool(approved),
            "approved_source": approved[0] if approved else None,
            "production_corpus_ingestion_allowed": bool(approved),
            "explanation": (
                "No source currently satisfies all required rights with a verifiable "
                "agreement reference. Phases 25-30 (production ingestion/training/"
                "calibration/benchmarking/integration) are BLOCKED until an approved "
                "source exists. The 396 dev records remain RIGHTS_UNVERIFIED."
            ),
        },
    }
    with open(RIGHTS_GATE, "w", encoding="utf-8") as f:
        json.dump(gate, f, indent=2, ensure_ascii=False)
    print(json.dumps(gate["gate"], indent=2, ensure_ascii=False))
    print(f"\nWROTE: {RIGHTS_GATE}")


if __name__ == "__main__":
    main()
