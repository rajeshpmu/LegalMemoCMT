from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

import pandas as pd


TIME_RE = re.compile(r"(?P<start>\d{2}:\d{2}:\d{2}[.,]\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}[.,]\d{3})")
TAG_RE = re.compile(r"<[^>]+>")
WITNESS_RE = re.compile(r"\b(witness|testimony|testifying|on the stand|called to testify)\b", re.I)
QUESTION_RE = re.compile(r"\?|\b(did|do|does|didn't|isn't|can you|would you|could you|were you|have you)\b", re.I)


def seconds(value: str) -> float:
    value = value.replace(",", ".")
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def clean_caption(value: str) -> str:
    value = html.unescape(value)
    value = TAG_RE.sub("", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_vtt(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    cues: list[dict[str, object]] = []
    i = 0
    while i < len(lines):
        match = TIME_RE.search(lines[i])
        if not match:
            i += 1
            continue
        start = seconds(match.group("start"))
        end = seconds(match.group("end"))
        body: list[str] = []
        i += 1
        while i < len(lines) and lines[i].strip():
            body.append(lines[i].strip())
            i += 1
        raw = " ".join(body)
        text = clean_caption(raw)
        cues.append({"start": start, "end": end, "text": text, "raw": raw, "has_marker": ">>" in raw})
        i += 1
    return cues


def row_times(row: dict[str, object]) -> tuple[float, float]:
    start = str(row.get("turn_start_time") or "").strip()
    end = str(row.get("turn_end_time") or "").strip()
    if start and end:
        return seconds(start), seconds(end)
    start = str(row.get("start_time") or "00:00:00.000")
    end = str(row.get("end_time") or start)
    offset = float(str(row.get("source_offset_seconds") or 0) or 0)
    return max(0.0, seconds(start) - offset), max(0.0, seconds(end) - offset)


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach conservative VTT evidence to a Clancy manifest")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.input_csv, dtype=str).fillna("")
    cache: dict[str, list[dict[str, object]]] = {}
    output: list[dict[str, str]] = []
    for _, source_row in df.iterrows():
        row = {key: str(value) for key, value in source_row.to_dict().items()}
        subtitle_path = row.get("subtitle_path", "")
        if subtitle_path not in cache:
            cache[subtitle_path] = parse_vtt(Path(subtitle_path)) if subtitle_path else []
        start, end = row_times(row)
        matches = [cue for cue in cache[subtitle_path] if float(cue["end"]) > start and float(cue["start"]) < end]
        evidence = " ".join(str(cue["text"]) for cue in matches if str(cue["text"]).strip())
        explicit_witness = bool(WITNESS_RE.search(evidence))
        question = bool(QUESTION_RE.search(evidence))
        row.update({
            "subtitle_cue_count": str(len(matches)),
            "subtitle_boundary_marker": "YES" if any(bool(cue["has_marker"]) for cue in matches) else "NO",
            "subtitle_question_pattern": "YES" if question else "NO",
            "subtitle_witness_term": "YES" if explicit_witness else "NO",
            "subtitle_evidence_text": evidence[:2000],
            "probable_testimony_block": "YES" if explicit_witness else "UNKNOWN",
            "witness_in_segment": "YES" if explicit_witness else "UNKNOWN",
            "witness_speaking_status": "UNKNOWN",
            "speaker_role": "UNKNOWN",
            "speaker_role_source": "subtitle_heuristic" if explicit_witness else "unresolved",
            "speaker_role_confidence": "LOW",
            "speaker_cluster_id": "UNKNOWN",
            "visual_target_role": "UNKNOWN",
            "visual_speaker_match": "UNKNOWN",
        })
        output.append(row)
    out = Path(args.output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(output).to_csv(out, index=False)
    print(f"Wrote {len(output)} subtitle-evidence rows to {out}")


if __name__ == "__main__":
    main()
