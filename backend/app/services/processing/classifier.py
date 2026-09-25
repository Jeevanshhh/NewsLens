"""Rule-based classification (Phase 3).

Ported from the notebook's ``detect_exam`` / ``detect_category`` /
``detect_state``. This is explicitly *keyword matching*, NOT a machine-learning
model. First match wins, with safe "Unknown"/"Other" fallbacks so no article
is silently discarded.
"""
from __future__ import annotations

from typing import Dict

from app.services.processing.domain_config import ClassificationConfig

_UNKNOWN_EXAM = {
    "Name of Exam": "Unknown",
    "Exam Category": "Unknown",
    "Board": "Unknown",
    "Conducted By": "Unknown",
    "PBT/CBT": "Unknown",
}


def detect_exam(text: str, config: ClassificationConfig) -> Dict[str, str]:
    upper = text.upper()
    for exam, info in config.exam_database.items():
        if exam.upper() in upper:
            return info
    return dict(_UNKNOWN_EXAM)


def detect_category(text: str, config: ClassificationConfig) -> str:
    low = text.lower()
    for category, words in config.category_keywords.items():
        for word in words:
            if word.lower() in low:
                return category
    return "Other"


def detect_state(text: str, config: ClassificationConfig) -> str:
    low = text.lower()
    for state in config.indian_states:
        if state.lower() in low:
            return state
    return "Unknown"
