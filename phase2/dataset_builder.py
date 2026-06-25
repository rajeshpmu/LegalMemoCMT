from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRIBUNAL_SOURCES = ROOT / "data" / "phase2" / "source_manifests" / "tribunal_sources_target_dataset.csv"
DEFAULT_WITNESS_MANIFEST = ROOT / "data" / "phase2" / "source_manifests" / "witness_harvest_manifest.csv"
DEFAULT_RESOLVED_MANIFEST = ROOT / "data" / "resolved_manifest.csv"
DEFAULT_RAW_DIR = ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = ROOT / "data" / "processed" / "phase2"
DEFAULT_REPORT_DIR = ROOT / "reports"


TRIBUNAL_REQUIRED_COLUMNS = {
    "subset_id",
    "tribunal",
    "case_family",
    "content_type",
    "source_url",
    "target_video_hours",
    "target_witnesses",
    "notes",
}

WITNESS_REQUIRED_COLUMNS = {
    "tribunal",
    "case_name",
    "hearing_date",
    "witness_name",
    "witness_type",
    "transcript_url",
    "video_url",
    "duration_minutes",
    "speaker_role",
    "download_status",
    "annotation_status",
    "utterance_count",
    "emotion_label_status",
    "credibility_label_status",
    "notes",
}

FINAL_COLUMNS = [
    "utterance_id",
    "manifest_id",
    "tribunal",
    "case_name",
    "speaker_role",
    "speaker_name",
    "utterance_text",
    "start_time",
    "end_time",
    "video_path",
    "audio_path",
    "emotion_label",
    "credibility_label",
    "question_type",
    "cross_examination_flag",
]


def _read_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df.copy()


def _missing_urls(df: pd.DataFrame, columns: Iterable[str]) -> list[int]:
    bad = []
    for idx, row in df.iterrows():
        if any(not str(row.get(col, "")).strip() for col in columns):
            bad.append(int(idx))
    return bad


def _normalize_id(*parts: object) -> str:
    text = "_".join(str(p).strip() for p in parts if str(p).strip())
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "item"


def _coerce_int(value: object, field: str, *, minimum: int = 1) -> int:
    try:
        ivalue = int(float(value))
    except Exception as exc:
        raise ValueError(f"Invalid {field}: {value}") from exc
    if ivalue < minimum:
        raise ValueError(f"Invalid {field}: {value}")
    return ivalue


def _ensure_required(df: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")


def load_tribunal_sources(path: str | Path = DEFAULT_TRIBUNAL_SOURCES) -> pd.DataFrame:
    df = _read_csv(path)
    _ensure_required(df, TRIBUNAL_REQUIRED_COLUMNS, "tribunal sources CSV")
    if df["subset_id"].duplicated().any():
        dups = df.loc[df["subset_id"].duplicated(), "subset_id"].tolist()
        raise ValueError(f"Duplicate subset_id values found: {dups}")

    if df["source_url"].isna().any() or (df["source_url"].astype(str).str.strip() == "").any():
        raise ValueError("tribunal sources CSV contains missing source_url values")

    for field in ["target_video_hours", "target_witnesses"]:
        invalid = []
        for idx, value in enumerate(df[field].tolist()):
            try:
                if float(value) <= 0:
                    invalid.append(idx)
            except Exception:
                invalid.append(idx)
        if invalid:
            raise ValueError(f"Invalid {field} values at rows: {invalid}")
    return df


def load_manifest(path: str | Path = DEFAULT_WITNESS_MANIFEST) -> pd.DataFrame:
    df = _read_csv(path)
    _ensure_required(df, WITNESS_REQUIRED_COLUMNS, "witness harvest manifest")
    df = df.copy()
    if "manifest_id" not in df.columns:
        df["manifest_id"] = [
            _normalize_id(row["tribunal"], row["case_name"], row.get("witness_name", ""), row.get("hearing_date", ""), i)
            for i, (_, row) in enumerate(df.iterrows(), start=1)
        ]
    else:
        df["manifest_id"] = df["manifest_id"].fillna("").astype(str).map(lambda x: x.strip() or None)
        missing_idx = df["manifest_id"].isna() | (df["manifest_id"].astype(str).str.strip() == "")
        if missing_idx.any():
            for i, idx in enumerate(df.index[missing_idx], start=1):
                row = df.loc[idx]
                df.at[idx, "manifest_id"] = _normalize_id(row["tribunal"], row["case_name"], row.get("witness_name", ""), row.get("hearing_date", ""), i)

    if df["manifest_id"].duplicated().any():
        dups = df.loc[df["manifest_id"].duplicated(), "manifest_id"].tolist()
        raise ValueError(f"Duplicate manifest_id values found: {dups}")

    for url_col in ["transcript_url", "video_url"]:
        if url_col in df.columns:
            missing = df[url_col].isna() | (df[url_col].astype(str).str.strip() == "")
            if missing.any():
                # We permit unresolved URLs but do not allow the field to be entirely empty.
                if missing.all():
                    raise ValueError(f"witness manifest has no usable URLs in {url_col}")

    for field in ["duration_minutes", "utterance_count"]:
        for idx, value in enumerate(df[field].tolist()):
            if pd.isna(value):
                continue
            try:
                if float(value) <= 0:
                    raise ValueError
            except Exception as exc:
                raise ValueError(f"Invalid {field} value at row {idx}: {value}") from exc

    duplicate_key = (
        df["tribunal"].fillna("").astype(str).str.strip().str.lower()
        + "::"
        + df["case_name"].fillna("").astype(str).str.strip().str.lower()
        + "::"
        + df["witness_name"].fillna("").astype(str).str.strip().str.lower()
        + "::"
        + df["witness_type"].fillna("").astype(str).str.strip().str.lower()
    )
    pair = duplicate_key
    if pair.duplicated().any():
        # We only flag true duplicates when the same case and witness code repeat.
        dup_rows = df.loc[pair.duplicated(), ["manifest_id", "tribunal", "case_name", "witness_name", "witness_type"]]
        if not dup_rows.empty:
            raise ValueError(
                "Duplicate witness entries found in the same witness/case slot: "
                + dup_rows.to_dict(orient="records").__repr__()
            )
    return df


def _fetch_page(url: str, timeout: int = 60) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"})
    resp.raise_for_status()
    return resp.text


def _candidate_links(page_url: str, keywords: Iterable[str]) -> list[str]:
    html = _fetch_page(page_url)
    soup = BeautifulSoup(html, "html.parser")
    keywords = [k.lower() for k in keywords if k]
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        text = " ".join(a.stripped_strings).lower()
        href_lower = href.lower()
        if keywords and not any(k in text or k in href_lower for k in keywords):
            continue
        if href not in links:
            links.append(href)
    return links


def resolve_transcript_links(row: pd.Series | dict[str, object]) -> str:
    source = str(row.get("transcript_url_to_resolve") or row.get("transcript_url") or row.get("source_evidence_url") or "").strip()
    if not source:
        return ""
    if source.lower().endswith((".pdf", ".txt", ".html", ".htm")):
        return source
    keywords = [
        str(row.get("tribunal", "")),
        str(row.get("case_name", "")),
        str(row.get("witness_name_or_code", "")),
        str(row.get("witness_name", "")),
    ]
    try:
        links = _candidate_links(source, keywords)
        for link in links:
            if any(link.lower().endswith(ext) for ext in (".pdf", ".txt", ".html", ".htm")):
                return link
        if links:
            return links[0]
    except Exception:
        pass
    return source


def resolve_video_links(row: pd.Series | dict[str, object]) -> str:
    source = str(row.get("video_url_to_resolve") or row.get("video_url") or row.get("source_evidence_url") or "").strip()
    if not source:
        return ""
    if source.lower().endswith((".mp4", ".webm", ".mov", ".mkv", ".mp3", ".wav")):
        return source
    keywords = [
        str(row.get("tribunal", "")),
        str(row.get("case_name", "")),
        str(row.get("witness_name_or_code", "")),
        str(row.get("witness_name", "")),
        "video",
    ]
    try:
        links = _candidate_links(source, keywords)
        for link in links:
            if any(link.lower().endswith(ext) for ext in (".mp4", ".webm", ".mov", ".mkv", ".mp3", ".wav")):
                return link
        if links:
            return links[0]
    except Exception:
        pass
    return source


def resolve_records(
    witness_manifest: pd.DataFrame,
    *,
    output_path: str | Path = DEFAULT_RESOLVED_MANIFEST,
) -> pd.DataFrame:
    rows = []
    for _, row in witness_manifest.iterrows():
        transcript_url = resolve_transcript_links(row)
        video_url = resolve_video_links(row)
        out = row.to_dict()
        out["resolved_transcript_url"] = transcript_url
        out["resolved_video_url"] = video_url
        out["resolution_status"] = "resolved" if transcript_url or video_url else "pending"
        rows.append(out)
    df = pd.DataFrame(rows)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df


def materialize_records(
    resolved_manifest: pd.DataFrame,
    *,
    transcripts_dir: str | Path = DEFAULT_RAW_DIR / "transcripts",
    videos_dir: str | Path = DEFAULT_RAW_DIR / "videos",
    audio_dir: str | Path = DEFAULT_RAW_DIR / "audio",
    output_path: str | Path = ROOT / "data" / "resolved_manifest_materialized.csv",
) -> pd.DataFrame:
    transcripts_dir = Path(transcripts_dir)
    videos_dir = Path(videos_dir)
    audio_dir = Path(audio_dir)
    rows: list[dict[str, object]] = []
    for _, row in resolved_manifest.iterrows():
        out = row.to_dict()
        manifest_id = str(out.get("manifest_id", "")).strip()
        transcript_url = str(out.get("resolved_transcript_url") or out.get("transcript_url") or "").strip()
        video_url = str(out.get("resolved_video_url") or out.get("video_url") or "").strip()

        local_transcript_path = str(out.get("local_transcript_path") or "").strip()
        if transcript_url and not local_transcript_path:
            try:
                local_transcript_path = str(download_transcript(transcript_url, manifest_id, output_dir=transcripts_dir))
            except Exception as exc:
                out["transcript_download_error"] = str(exc)

        local_video_path = str(out.get("local_video_path") or "").strip()
        if video_url and not local_video_path:
            try:
                local_video_path = str(download_video(video_url, manifest_id, output_dir=videos_dir))
            except Exception as exc:
                out["video_download_error"] = str(exc)

        local_audio_path = str(out.get("local_audio_path") or "").strip()
        if local_video_path and not local_audio_path:
            try:
                local_audio_path = str(extract_audio(local_video_path, output_dir=audio_dir))
            except Exception as exc:
                out["audio_extraction_error"] = str(exc)

        out["local_transcript_path"] = local_transcript_path
        out["local_video_path"] = local_video_path
        out["local_audio_path"] = local_audio_path
        out["materialization_status"] = "ready" if local_transcript_path or local_video_path else "pending"
        rows.append(out)

    df = pd.DataFrame(rows)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df


def _download(url: str, dest: Path, *, timeout: int = 120) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=timeout, stream=True, headers={"User-Agent": "LegalMemoCMT-Phase2/1.0"}) as resp:
        resp.raise_for_status()
        with dest.open("wb") as out:
            for chunk in resp.iter_content(chunk_size=1024 * 128):
                if chunk:
                    out.write(chunk)
    return dest


def download_transcript(url: str, manifest_id: str, *, output_dir: str | Path = DEFAULT_RAW_DIR / "transcripts") -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(urlparse(url).path).suffix or ".txt"
    dest = out_dir / f"{manifest_id}{suffix}"
    return _download(url, dest)


def extract_transcript_text(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        if PdfReader is None:
            raise ImportError("pypdf is required for PDF transcript extraction")
        reader = PdfReader(str(p))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if suffix in {".html", ".htm"}:
        html = p.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()
    return p.read_text(encoding="utf-8", errors="ignore").strip()


def download_video(url: str, manifest_id: str, *, output_dir: str | Path = DEFAULT_RAW_DIR / "videos") -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(urlparse(url).path).suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".webm", ".mp3", ".wav"}:
        suffix = ".mp4"
    dest = out_dir / f"{manifest_id}{suffix}"
    return _download(url, dest)


def extract_audio(video_path: str | Path, *, output_dir: str | Path = DEFAULT_RAW_DIR / "audio") -> Path:
    src = Path(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{src.stem}.wav"
    if src.suffix.lower() in {".mp3", ".wav"}:
        if src.resolve() != dest.resolve():
            dest.write_bytes(src.read_bytes())
        return dest
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest


SPEAKER_PATTERNS = [
    (re.compile(r"^(judge|the court|presiding judge|panel judge|mrs?\.?\s+justice)\b[:\-]?\s*(.*)$", re.I), "judge"),
    (re.compile(r"^(prosecutor|mr\.?\s+prosecutor|ms\.?\s+prosecutor)\b[:\-]?\s*(.*)$", re.I), "prosecutor"),
    (re.compile(r"^(defense|defence|defense counsel|defence counsel|mr\.?\s+defense|ms\.?\s+defense)\b[:\-]?\s*(.*)$", re.I), "defense counsel"),
    (re.compile(r"^(witness|the witness)\b[:\-]?\s*(.*)$", re.I), "witness"),
    (re.compile(r"^(q\.?|question)\b[:\-]?\s*(.*)$", re.I), "question"),
    (re.compile(r"^(a\.?|answer)\b[:\-]?\s*(.*)$", re.I), "answer"),
]


def segment_transcript(
    text: str,
    *,
    manifest_id: str,
    default_speaker: str = "witness",
    default_role: str = "witness",
) -> list[dict[str, object]]:
    lines = [ln.strip() for ln in re.split(r"\n+", text or "") if ln.strip()]
    utterances: list[dict[str, object]] = []
    current_speaker = default_speaker
    current_role = default_role
    idx = 0

    for line in lines:
        speaker = current_speaker
        role = current_role
        text_part = line
        for pattern, mapped_role in SPEAKER_PATTERNS:
            m = pattern.match(line)
            if m:
                speaker = m.group(1).strip().title()
                role = mapped_role
                text_part = m.group(2).strip()
                break
        if line.startswith("Q:") or line.startswith("Q."):
            speaker = "Questioner"
            role = "question"
            text_part = line[2:].strip(" :-")
        elif line.startswith("A:") or line.startswith("A."):
            speaker = "Witness"
            role = "answer"
            text_part = line[2:].strip(" :-")
        if not text_part:
            continue
        idx += 1
        utterances.append(
            {
                "utterance_id": f"{manifest_id}_utt{idx:05d}",
                "speaker": speaker,
                "role": role,
                "text": text_part,
                "start_time": "",
                "end_time": "",
            }
        )
        current_speaker = speaker
        current_role = role
    return utterances


def _infer_emotion_label(text: str) -> str:
    txt = text.lower()
    rules = [
        ("fear", ["fear", "afraid", "scared", "terrified", "anxious", "nervous", "worried"]),
        ("anger", ["angry", "furious", "irritated", "objection", "hostile", "upset"]),
        ("sadness", ["sad", "cry", "crying", "grief", "tearful", "distressed"]),
        ("stress", ["stress", "strained", "pressure", "overwhelmed", "tired", "exhausted", "difficult"]),
        ("confidence", ["certain", "confident", "sure", "clear", "absolutely", "definitely"]),
    ]
    for label, tokens in rules:
        if any(tok in txt for tok in tokens):
            return label
    return "neutral"


def _infer_question_type(text: str, role: str) -> str:
    txt = text.strip().lower()
    if role in {"judge"}:
        return "clarification" if "clarify" in txt or "explain" in txt else "open"
    if role in {"prosecutor", "defense counsel"}:
        if "isn't it" in txt or "would you agree" in txt or txt.startswith(("did you", "were you", "was it", "is it")):
            return "leading"
        if txt.endswith("?"):
            return "closed" if txt.startswith(("did", "do", "does", "was", "were", "is", "are", "can", "could", "have", "has", "had")) else "open"
        return "cross examination"
    if txt.endswith("?"):
        return "closed" if txt.startswith(("did", "do", "does", "was", "were", "is", "are", "can", "could", "have", "has", "had")) else "open"
    return "clarification" if "what do you mean" in txt else "open"


def _infer_credibility(text: str) -> str:
    txt = text.lower()
    if any(term in txt for term in ["i don't recall", "i do not recall", "maybe", "perhaps", "not sure", "cannot remember", "can't remember"]):
        return "uncertain"
    if any(term in txt for term in ["not true", "incorrect", "contradiction", "contradict", "inconsistent"]):
        return "contradictory"
    return "consistent"


def build_final_dataset(
    resolved_manifest: pd.DataFrame,
    *,
    transcripts_dir: str | Path = DEFAULT_RAW_DIR / "transcripts",
    videos_dir: str | Path = DEFAULT_RAW_DIR / "videos",
    audio_dir: str | Path = DEFAULT_RAW_DIR / "audio",
    output_csv: str | Path = DEFAULT_PROCESSED_DIR / "legalmemocmt_phase2_dataset.csv",
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    transcripts_dir = Path(transcripts_dir)
    videos_dir = Path(videos_dir)
    audio_dir = Path(audio_dir)
    for _, row in resolved_manifest.iterrows():
        manifest_id = str(row["manifest_id"])
        transcript_path = row.get("local_transcript_path") or row.get("transcript_local_path") or ""
        if not transcript_path:
            resolved_url = str(row.get("resolved_transcript_url") or row.get("transcript_url") or "")
            if resolved_url:
                transcript_path = transcripts_dir / f"{manifest_id}{Path(urlparse(resolved_url).path).suffix or '.txt'}"
        transcript_path = Path(str(transcript_path)) if str(transcript_path).strip() else None
        transcript_text = extract_transcript_text(transcript_path) if transcript_path and transcript_path.exists() else str(row.get("transcript_text", "") or "")
        video_path = row.get("local_video_path") or row.get("video_local_path") or row.get("video_path") or ""
        audio_path = row.get("local_audio_path") or row.get("audio_local_path") or row.get("audio_path") or ""
        video_path = str(video_path).strip()
        audio_path = str(audio_path).strip()
        if not audio_path and video_path:
            try:
                audio_path = str(extract_audio(video_path, output_dir=audio_dir))
            except Exception:
                audio_path = ""
        for utt in segment_transcript(
            transcript_text,
            manifest_id=manifest_id,
            default_speaker=str(row.get("witness_name", "") or row.get("witness_name_or_code", "") or "witness"),
            default_role=str(row.get("speaker_role", "witness") or "witness"),
        ):
            speaker_role = str(utt["role"])
            text = str(utt["text"])
            rows.append(
                {
                    "utterance_id": utt["utterance_id"],
                    "manifest_id": manifest_id,
                    "tribunal": row.get("tribunal", ""),
                    "case_name": row.get("case_name", ""),
                    "speaker_role": speaker_role,
                    "speaker_name": row.get("witness_name", "") or row.get("witness_name_or_code", ""),
                    "utterance_text": text,
                    "start_time": utt.get("start_time", ""),
                    "end_time": utt.get("end_time", ""),
                    "video_path": video_path,
                    "audio_path": audio_path,
                    "emotion_label": _infer_emotion_label(text),
                    "credibility_label": _infer_credibility(text),
                    "question_type": _infer_question_type(text, speaker_role),
                    "cross_examination_flag": int(speaker_role in {"prosecutor", "defense counsel"}),
                }
            )
    df = pd.DataFrame(rows, columns=FINAL_COLUMNS)
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    return df


def generate_weak_labels(dataset: pd.DataFrame, *, output_dir: str | Path = DEFAULT_PROCESSED_DIR / "weak_labels") -> dict[str, pd.DataFrame]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    emotion = dataset[["utterance_id", "emotion_label"]].copy()
    question = dataset[["utterance_id", "question_type"]].copy()
    credibility = dataset[["utterance_id", "credibility_label"]].copy()
    emotion.to_csv(out_dir / "emotion_labels.csv", index=False)
    question.to_csv(out_dir / "question_type_labels.csv", index=False)
    credibility.to_csv(out_dir / "credibility_labels.csv", index=False)
    return {"emotion": emotion, "question_type": question, "credibility": credibility}


def build_dashboard(dataset: pd.DataFrame, resolved_manifest: pd.DataFrame, *, output_html: str | Path = DEFAULT_REPORT_DIR / "dataset_status.html") -> Path:
    out = Path(output_html)
    out.parent.mkdir(parents=True, exist_ok=True)
    witnesses = resolved_manifest["witness_name"].fillna("").astype(str).nunique() if "witness_name" in resolved_manifest.columns else 0
    hours = 0.0
    if "duration_minutes" in resolved_manifest.columns:
        hours = float(pd.to_numeric(resolved_manifest["duration_minutes"], errors="coerce").fillna(0).sum()) / 60.0
    total_utterances = len(dataset)
    transcript_coverage = float(dataset["utterance_text"].astype(str).str.strip().ne("").mean() * 100.0) if not dataset.empty else 0.0
    video_coverage = float(dataset["video_path"].astype(str).str.strip().ne("").mean() * 100.0) if not dataset.empty else 0.0
    annotation_coverage = float(dataset["emotion_label"].astype(str).str.strip().ne("neutral").mean() * 100.0) if not dataset.empty else 0.0
    html = f"""
    <html>
      <head><title>LegalMemoCMT Phase 2 Dataset Status</title></head>
      <body style="font-family: Arial, sans-serif;">
        <h1>LegalMemoCMT Phase 2 Dataset Status</h1>
        <ul>
          <li>Witnesses collected: {witnesses}</li>
          <li>Hours collected: {hours:.2f}</li>
          <li>Utterances collected: {total_utterances}</li>
          <li>Transcript coverage: {transcript_coverage:.2f}%</li>
          <li>Video coverage: {video_coverage:.2f}%</li>
          <li>Annotation coverage: {annotation_coverage:.2f}%</li>
        </ul>
      </body>
    </html>
    """
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="LegalMemoCMT Phase 2 dataset builder")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate-tri")
    sub.add_parser("validate-witness")

    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("--witness-manifest", default=str(DEFAULT_WITNESS_MANIFEST))
    p_resolve.add_argument("--output", default=str(DEFAULT_RESOLVED_MANIFEST))

    p_download_t = sub.add_parser("download-transcript")
    p_download_t.add_argument("--url", required=True)
    p_download_t.add_argument("--manifest-id", required=True)
    p_download_t.add_argument("--output-dir", default=str(DEFAULT_RAW_DIR / "transcripts"))

    p_download_v = sub.add_parser("download-video")
    p_download_v.add_argument("--url", required=True)
    p_download_v.add_argument("--manifest-id", required=True)
    p_download_v.add_argument("--output-dir", default=str(DEFAULT_RAW_DIR / "videos"))

    p_extract_a = sub.add_parser("extract-audio")
    p_extract_a.add_argument("--video-path", required=True)
    p_extract_a.add_argument("--output-dir", default=str(DEFAULT_RAW_DIR / "audio"))

    p_segment = sub.add_parser("segment")
    p_segment.add_argument("--text-file", required=True)
    p_segment.add_argument("--manifest-id", required=True)
    p_segment.add_argument("--output-json", required=True)

    p_build = sub.add_parser("build-dataset")
    p_build.add_argument("--resolved-manifest", default=str(DEFAULT_RESOLVED_MANIFEST))
    p_build.add_argument("--output-csv", default=str(DEFAULT_PROCESSED_DIR / "legalmemocmt_phase2_dataset.csv"))

    p_mat = sub.add_parser("materialize")
    p_mat.add_argument("--resolved-manifest", default=str(DEFAULT_RESOLVED_MANIFEST))
    p_mat.add_argument("--output", default=str(ROOT / "data" / "resolved_manifest_materialized.csv"))
    p_mat.add_argument("--transcripts-dir", default=str(DEFAULT_RAW_DIR / "transcripts"))
    p_mat.add_argument("--videos-dir", default=str(DEFAULT_RAW_DIR / "videos"))
    p_mat.add_argument("--audio-dir", default=str(DEFAULT_RAW_DIR / "audio"))

    p_weak = sub.add_parser("weak-labels")
    p_weak.add_argument("--dataset-csv", default=str(DEFAULT_PROCESSED_DIR / "legalmemocmt_phase2_dataset.csv"))
    p_weak.add_argument("--output-dir", default=str(DEFAULT_PROCESSED_DIR / "weak_labels"))

    p_dash = sub.add_parser("dashboard")
    p_dash.add_argument("--dataset-csv", default=str(DEFAULT_PROCESSED_DIR / "legalmemocmt_phase2_dataset.csv"))
    p_dash.add_argument("--resolved-manifest", default=str(DEFAULT_RESOLVED_MANIFEST))
    p_dash.add_argument("--output-html", default=str(DEFAULT_REPORT_DIR / "dataset_status.html"))

    args = parser.parse_args()

    if args.command == "validate-tri":
        df = load_tribunal_sources()
        print(df.head().to_string())
    elif args.command == "validate-witness":
        df = load_manifest()
        print(df.head().to_string())
    elif args.command == "resolve":
        df = resolve_records(load_manifest(args.witness_manifest), output_path=args.output)
        print(df.head().to_string())
    elif args.command == "download-transcript":
        path = download_transcript(args.url, args.manifest_id, output_dir=args.output_dir)
        print(path)
    elif args.command == "download-video":
        path = download_video(args.url, args.manifest_id, output_dir=args.output_dir)
        print(path)
    elif args.command == "extract-audio":
        path = extract_audio(args.video_path, output_dir=args.output_dir)
        print(path)
    elif args.command == "segment":
        text = Path(args.text_file).read_text(encoding="utf-8", errors="ignore")
        rows = segment_transcript(text, manifest_id=args.manifest_id)
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"Wrote {len(rows)} utterances to {args.output_json}")
    elif args.command == "build-dataset":
        resolved = pd.read_csv(args.resolved_manifest)
        df = build_final_dataset(resolved, output_csv=args.output_csv)
        print(df.head().to_string())
    elif args.command == "materialize":
        resolved = pd.read_csv(args.resolved_manifest)
        df = materialize_records(
            resolved,
            transcripts_dir=args.transcripts_dir,
            videos_dir=args.videos_dir,
            audio_dir=args.audio_dir,
            output_path=args.output,
        )
        print(df.head().to_string())
    elif args.command == "weak-labels":
        dataset = pd.read_csv(args.dataset_csv)
        out = generate_weak_labels(dataset, output_dir=args.output_dir)
        print({k: len(v) for k, v in out.items()})
    elif args.command == "dashboard":
        dataset = pd.read_csv(args.dataset_csv)
        resolved = pd.read_csv(args.resolved_manifest)
        path = build_dashboard(dataset, resolved, output_html=args.output_html)
        print(path)


if __name__ == "__main__":
    main()
