from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

from .common import read_csv_rows, write_csv


LABELS = {
    0: "neutral",
    1: "fear",
    2: "anxiety",
    3: "anger",
    4: "stress",
    5: "sadness",
    6: "uncertain",
}

FEAR_TERMS = {
    "afraid", "fear", "scared", "terrified", "frightened", "panic", "panicked", "nervous", "worried", "anxious",
    "tense", "alarmed", "dar", "bhay", "gabhra", "tension",
}
ANGER_TERMS = {
    "angry", "furious", "irritated", "annoyed", "resentful", "hostile", "upset", "objection", "protest",
    "rage", "gussa", "krodh", "aakrosh",
}
STRESS_TERMS = {
    "stress", "stressed", "pressure", "burden", "overwhelmed", "tired", "exhausted", "strained", "tense",
    "unable", "cannot", "can't", "couldn't", "problem", "difficulty", "difficult", "dabaav", "thaka", "thak",
}
SADNESS_TERMS = {
    "sad", "sorrow", "grief", "cry", "crying", "tearful", "distressed", "downcast", "depressed",
}
UNCERTAINTY_TERMS = {
    "don't recall", "cannot recall", "can't recall", "not sure", "uncertain", "maybe", "perhaps", "I think",
    "I guess", "I do not know", "not remember", "memory", "blur", "unclear",
}
NEGATION_RE = re.compile(r"\b(no|not|never|none|nothing|nobody|without)\b", re.I)


def count_terms(text: str, terms: set[str]) -> int:
    lowered = text.lower()
    score = 0
    for term in terms:
        if " " in term:
            score += lowered.count(term)
        else:
            score += len(re.findall(rf"\b{re.escape(term)}\b", lowered))
    return score


def score_emotions(text: str) -> dict[str, float]:
    text = text or ""
    total_words = max(len(text.split()), 1)
    fear = count_terms(text, FEAR_TERMS) / math.sqrt(total_words)
    anger = count_terms(text, ANGER_TERMS) / math.sqrt(total_words)
    stress = count_terms(text, STRESS_TERMS) / math.sqrt(total_words)
    sadness = count_terms(text, SADNESS_TERMS) / math.sqrt(total_words)
    uncertainty = count_terms(text, UNCERTAINTY_TERMS) / math.sqrt(total_words)
    neutral = max(0.0, 1.0 - min(fear + anger + stress + sadness + uncertainty, 1.0))
    return {
        "neutral": neutral,
        "fear": fear,
        "anxiety": 0.5 * fear + 0.7 * uncertainty,
        "anger": anger,
        "stress": stress + 0.4 * uncertainty,
        "sadness": sadness,
        "uncertain": uncertainty,
    }


def choose_label(scores: dict[str, float]) -> tuple[int, str, float, str]:
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_label, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0
    confidence = max(0.0, min(1.0, top_score - second_score + 0.35))
    if scores["uncertain"] > max(scores["fear"], scores["anger"], scores["stress"], scores["sadness"]) and scores["uncertain"] > 0:
        return 6, "uncertain", confidence, "uncertainty_lexicon"
    if scores["anger"] >= scores["fear"] and scores["anger"] >= scores["stress"] and scores["anger"] >= scores["sadness"] and scores["anger"] > 0:
        return 3, "anger", confidence, "anger_lexicon"
    if scores["fear"] >= scores["stress"] and scores["fear"] >= scores["sadness"] and scores["fear"] > 0:
        if scores["anxiety"] >= scores["fear"] * 0.8:
            return 2, "anxiety", confidence, "fear_plus_uncertainty"
        return 1, "fear", confidence, "fear_lexicon"
    if scores["stress"] >= scores["sadness"] and scores["stress"] > 0:
        return 4, "stress", confidence, "stress_lexicon"
    if scores["sadness"] > 0:
        return 5, "sadness", confidence, "sadness_lexicon"
    return 0, "neutral", 0.45, "default_neutral"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate weak supervision labels for Phase 2 courtroom data")
    parser.add_argument("--input-csv", type=str, required=True, help="Input manifest or corpus CSV")
    parser.add_argument("--output-csv", type=str, required=True, help="Output weak-label CSV")
    parser.add_argument("--text-column", type=str, default="transcript", help="Column containing text to score")
    parser.add_argument("--min-confidence", type=float, default=0.35, help="Minimum confidence before marking as uncertain")
    args = parser.parse_args()

    rows = read_csv_rows(Path(args.input_csv))
    out_rows: list[dict[str, object]] = []
    for row in rows:
        text = (row.get(args.text_column) or row.get("text") or "").strip()
        if not text:
            continue
        scores = score_emotions(text)
        label_id, label_text, confidence, rule_name = choose_label(scores)
        if confidence < args.min_confidence:
            label_id, label_text = 6, "uncertain"
            rule_name = "low_confidence_fallback"
        out_rows.append(
            {
                "sample_id": row.get("sample_id", ""),
                "case_id": row.get("case_id", ""),
                "source_type": row.get("source_type", ""),
                "label": label_id,
                "label_text": label_text,
                "confidence": round(float(confidence), 4),
                "weak_rule": rule_name,
                "neutral_score": round(scores["neutral"], 4),
                "fear_score": round(scores["fear"], 4),
                "anxiety_score": round(scores["anxiety"], 4),
                "anger_score": round(scores["anger"], 4),
                "stress_score": round(scores["stress"], 4),
                "sadness_score": round(scores["sadness"], 4),
                "uncertain_score": round(scores["uncertain"], 4),
                "matched_text_length": len(text.split()),
            }
        )

    write_csv(
        Path(args.output_csv),
        out_rows,
        [
            "sample_id",
            "case_id",
            "source_type",
            "label",
            "label_text",
            "confidence",
            "weak_rule",
            "neutral_score",
            "fear_score",
            "anxiety_score",
            "anger_score",
            "stress_score",
            "sadness_score",
            "uncertain_score",
            "matched_text_length",
        ],
    )
    print(f"Wrote {len(out_rows)} weak labels to {args.output_csv}")


if __name__ == "__main__":
    main()

