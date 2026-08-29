"""Classify emotion target and temporal scope with one DeBERTa NLI model.

The original scope fields are preserved. This script writes model-specific
suggestions and score evidence; it does not create gold annotations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

MODEL = "MoritzLaurer/deberta-v3-large-zeroshot-v2.0"
TARGET_LABELS = {
    "SELF_EXPRESSED": "The witness is describing their own emotional state.",
    "OTHER_PERSON_DESCRIBED": "The witness is describing another person's emotional state.",
    "QUOTED_SPEECH": "The witness is reporting or quoting another person's emotional statement.",
    "EVENT_DESCRIBED": "The emotional content describes an event or situation rather than a person's emotion.",
    "NO_EMOTION_CONTENT": "The statement contains no meaningful emotional content.",
    "MIXED": "The statement contains emotional content involving multiple targets.",
    "UNCLEAR": "It is unclear whose emotional state is being described.",
}
TEMPORAL_LABELS = {
    "CURRENT": "The emotional state refers to the witness's current state while speaking.",
    "PAST_SELF": "The witness is describing their own emotional state at an earlier time.",
    "PAST_OTHER": "The witness is describing another person's emotional state at an earlier time.",
    "HYPOTHETICAL": "The emotional state is hypothetical or conditional.",
    "UNCLEAR": "The timing of the emotional state cannot be determined.",
}


def context(row: pd.Series, max_chars: int) -> str:
    previous = str(row.get("previous_question_text", "") or "").strip()
    text = str(row.get("utterance_text", "") or row.get("turn_text", "") or "").strip()
    value = f"Question/context:\n{previous}\nStatement:\n{text}" if previous else text
    return value[:max_chars]


def classify(pipe, text: str, labels: dict[str, str]) -> tuple[str, float, dict[str, float]]:
    result = pipe(
        text,
        list(labels.values()),
        hypothesis_template="{}",
        multi_label=False,
    )
    reverse = {description: name for name, description in labels.items()}
    scores = {reverse[label]: round(float(score), 6) for label, score in zip(result["labels"], result["scores"])}
    best = result["labels"][0]
    return reverse[best], round(float(result["scores"][0]), 6), scores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", required=True)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--device", default="-1", help="Transformers pipeline device; -1=CPU, 0=first GPU")
    parser.add_argument("--context-chars", type=int, default=3000)
    args = parser.parse_args()

    from transformers import pipeline

    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    if args.max_rows > 0:
        df = df.head(args.max_rows).copy()
    if df.empty:
        raise SystemExit("No rows selected")
    classifier = pipeline("zero-shot-classification", model=args.model, device=int(args.device))

    target_counts: dict[str, int] = {}
    temporal_counts: dict[str, int] = {}
    for index, row in df.iterrows():
        text = context(row, args.context_chars)
        if not text.strip():
            df.at[index, "deberta_target_scope"] = "UNCLEAR"
            df.at[index, "deberta_target_scope_confidence"] = "0.0"
            df.at[index, "deberta_temporal_scope"] = "UNCLEAR"
            df.at[index, "deberta_temporal_scope_confidence"] = "0.0"
            continue
        target, target_score, target_scores = classify(classifier, text, TARGET_LABELS)
        # Sequential design: temporal inference receives the target result so
        # that past/current interpretation is conditioned on the first step.
        temporal_text = f"Target interpretation: {TARGET_LABELS[target]}\n{text}"
        temporal, temporal_score, temporal_scores = classify(classifier, temporal_text, TEMPORAL_LABELS)
        df.at[index, "deberta_model"] = args.model
        df.at[index, "deberta_context"] = text
        df.at[index, "deberta_target_scope"] = target
        df.at[index, "deberta_target_scope_confidence"] = str(target_score)
        df.at[index, "deberta_target_scope_scores"] = json.dumps(target_scores, sort_keys=True)
        df.at[index, "deberta_temporal_scope"] = temporal
        df.at[index, "deberta_temporal_scope_confidence"] = str(temporal_score)
        df.at[index, "deberta_temporal_scope_scores"] = json.dumps(temporal_scores, sort_keys=True)
        df.at[index, "deberta_scope_annotation_status"] = "AUTO_SUGGESTED"
        target_counts[target] = target_counts.get(target, 0) + 1
        temporal_counts[temporal] = temporal_counts.get(temporal, 0) + 1

    out = Path(args.output_csv); out.parent.mkdir(parents=True, exist_ok=True); df.to_csv(out, index=False)
    summary = {
        "input_csv": args.input_csv, "output_csv": args.output_csv,
        "model": args.model, "rows_processed": len(df),
        "target_scope_counts": target_counts, "temporal_scope_counts": temporal_counts,
        "notes": [
            "The same DeBERTa zero-shot NLI model is used sequentially for target scope and temporal scope.",
            "Natural-language hypotheses are used instead of bare class tokens.",
            "The original emotion_target_scope and other annotation fields are preserved.",
            "Outputs are machine suggestions and require human review; no emotion, credibility, or deception label is inferred.",
        ],
    }
    report = Path(args.summary_json); report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
