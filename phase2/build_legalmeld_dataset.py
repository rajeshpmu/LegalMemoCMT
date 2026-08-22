from __future__ import annotations

import argparse
import csv
import audioop
import json
import math
import re
import subprocess
import sys
import wave
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

try:
    from faster_whisper import WhisperModel
except Exception:  # pragma: no cover
    WhisperModel = None  # type: ignore[assignment]

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from phase2.common import download_file, ensure_dir, group_case_splits, read_csv_rows, sha1_short, write_csv
    from phase2.trimodal_validation_utils import (
        extract_transcript_text,
        ffmpeg_exe,
        maybe_download_transcript,
        normalize_case_number,
        normalize_text,
        probe_media_url,
    )
else:
    from .common import download_file, ensure_dir, group_case_splits, read_csv_rows, sha1_short, write_csv
    from .trimodal_validation_utils import (
        extract_transcript_text,
        ffmpeg_exe,
        maybe_download_transcript,
        normalize_case_number,
        normalize_text,
        probe_media_url,
    )


HEARING_MANIFEST = Path("data/processed/phase2/hearing_manifest_validated.csv")
MEDIA_MANIFEST = Path("data/phase2/ucr_case_video_strict/index/ucr_case_videos_strict.csv")
SELECTION_MANIFEST = Path("data/processed/phase2/trimodal_corpus_selection.csv")
SOURCE_OFFSET_MANIFEST = Path("data/processed/phase2/hearing_source_offsets.csv")
OUTPUT_ROOT = Path("data/processed/phase2/legalmeld")

MASTER_COLUMNS = [
    "utterance_id",
    "hearing_id",
    "tribunal",
    "case_number",
    "case_family",
    "hearing_date",
    "source_offset_seconds",
    "witness_id",
    "speaker_role",
    "speaker_name",
    "examination_type",
    "utterance_text",
    "start_time",
    "end_time",
    "duration_ms",
    "video_clip",
    "audio_clip",
    "transcript_source",
    "alignment_status",
    "alignment_score",
    "alignment_method",
    "alignment_confidence",
    "asr_text",
    "transcript_text_normalized",
    "text_similarity",
    "clip_duration_seconds",
    "word_timestamp_count",
    "manual_review_required",
    "split_group_id",
    "split_strategy",
    "quality_tier",
    "audio_present",
    "audio_rms",
    "silence_ratio",
    "clipping_ratio",
    "sample_rate",
    "audio_validation_status",
    "face_detected",
    "face_visible_ratio",
    "shot_type",
    "speaker_visible",
    "video_quality_status",
    "emotion",
    "credibility",
    "split",
]

MELD_COLUMNS = [
    "Dialogue_ID",
    "Utterance_ID",
    "Utterance",
    "Speaker",
    "SpeakerRole",
    "WitnessID",
    "Emotion",
    "Credibility",
    "CaseNumber",
    "CaseFamily",
    "HearingDate",
    "SourceOffsetSeconds",
    "ExaminationType",
    "StartTime",
    "EndTime",
    "DurationMs",
    "VideoPath",
    "AudioPath",
    "TranscriptSource",
    "AlignmentStatus",
    "AlignmentScore",
    "AlignmentMethod",
    "AlignmentConfidence",
    "ASRText",
    "TranscriptTextNormalized",
    "TextSimilarity",
    "ClipDurationSeconds",
    "WordTimestampCount",
    "ManualReviewRequired",
    "SplitGroupId",
    "SplitStrategy",
    "QualityTier",
    "AudioPresent",
    "AudioRMS",
    "SilenceRatio",
    "ClippingRatio",
    "SampleRate",
    "AudioValidationStatus",
    "FaceDetected",
    "FaceVisibleRatio",
    "ShotType",
    "SpeakerVisible",
    "VideoQualityStatus",
]

SPEAKER_LABEL_RE = re.compile(r"^(?P<label>[A-Z][A-Z0-9 .,'()\/\-]{1,80})\s*:\s*(?P<text>.*)$")
QA_RE = re.compile(r"^(?P<label>[QA])\s*[:.]\s*(?P<text>.*)$", re.I)
PAGE_RE = re.compile(r"^\s*(?:page\s+\d+|\d{1,5})\s*$", re.I)
APPEARANCE_SECTION_RE = re.compile(r"^\s*for the (prosecution|defence|defense|accused|registry)\b", re.I)
PROCEEDINGS_MARKERS = ("P R O C E E D I N G S", "PROCEEDINGS")
STOPWORDS = {
    "the",
    "and",
    "or",
    "to",
    "a",
    "of",
    "in",
    "for",
    "is",
    "it",
    "that",
    "this",
    "i",
    "you",
    "we",
    "he",
    "she",
    "they",
    "on",
    "with",
    "as",
    "at",
    "by",
}

HIGH_CONFIDENCE_ALIGNMENT_SCORE = 0.7
HIGH_CONFIDENCE_TEXT_SIMILARITY = 0.5
MEDIUM_CONFIDENCE_ALIGNMENT_SCORE = 0.35
MEDIUM_CONFIDENCE_TEXT_SIMILARITY = 0.2
REVIEW_TEXT_SIMILARITY = 0.25


@dataclass
class TokenWord:
    token: str
    start: float
    end: float


@dataclass
class Utterance:
    speaker: str
    role: str
    text: str
    label: str


def _clean_line(line: str) -> str:
    text = normalize_text(line)
    if not text:
        return ""
    text = re.sub(r"^\s*\d{1,5}\s+", "", text)
    text = re.sub(r"^\s*page\s+\d+\s*", "", text, flags=re.I)
    return normalize_text(text)


def _transcript_body(text: str) -> str:
    lines = text.splitlines()
    for idx, raw in enumerate(lines):
        cleaned = _clean_line(raw).upper()
        compact = cleaned.replace(" ", "")
        if cleaned in {"P R O C E E D I N G S", "PROCEEDINGS"} or compact == "PROCEEDINGS":
            return "\n".join(lines[idx:])
    return text


def _normalize_token(token: str) -> str:
    token = token.lower()
    token = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", token)
    return token


def _tokenize(text: str) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    raw = re.findall(r"[A-Za-z0-9']+", text)
    tokens = []
    for item in raw:
        tok = _normalize_token(item)
        if tok:
            tokens.append(tok)
    return tokens


def _significant_tokens(tokens: list[str]) -> list[str]:
    out = [tok for tok in tokens if tok not in STOPWORDS]
    return out or tokens


def _parse_appearance_map(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    section_role = ""
    for raw in text.splitlines():
        line = _clean_line(raw)
        if not line:
            continue
        cleaned = line.upper().replace(" ", "")
        if cleaned == "PROCEEDINGS":
            break
        if APPEARANCE_SECTION_RE.match(line):
            section = line.lower()
            if "prosecution" in section:
                section_role = "Prosecutor"
            elif "defence" in section or "defense" in section or "accused" in section:
                section_role = "Defence"
            elif "registry" in section:
                section_role = "Judge"
            continue
        if line.lower().startswith("court reporters"):
            break
        if not section_role:
            continue
        names = [n.strip() for n in re.split(r",| and ", line) if n.strip()]
        for name in names:
            name = re.sub(r"^[A-Z][a-z]+\.\s+", "", name).strip()
            if not name:
                continue
            mapping[name.upper()] = section_role
            last = name.split()[-1].upper()
            mapping[last] = section_role
    return mapping


def _classify_role(label: str, appearance_map: dict[str, str], fallback_role: str = "Prosecutor") -> str:
    text = normalize_text(label)
    up = text.upper()
    if not text:
        return fallback_role
    if "WITNESS" in up:
        return "Witness"
    if any(term in up for term in ["JUDGE", "PRESIDENT", "COURT", "REGISTRAR"]):
        return "Judge"
    if up in {"Q", "QUESTION"}:
        return fallback_role
    if up in {"A", "ANSWER"}:
        return "Witness"
    if "PROSECUTOR" in up:
        return "Prosecutor"
    if "DEFENCE" in up or "DEFENSE" in up or "COUNSEL" in up:
        return "Defence"
    candidates = [up, up.split()[-1]]
    for cand in candidates:
        if cand in appearance_map:
            return appearance_map[cand]
    return fallback_role


def segment_transcript(text: str, *, witness_id: str, default_examination_type: str = "unknown") -> list[Utterance]:
    appearance_map = _parse_appearance_map(text)
    body = _transcript_body(text)
    lines = [_clean_line(line) for line in body.splitlines()]
    utterances: list[Utterance] = []
    current_speaker = ""
    current_role = ""
    current_label = ""
    current_text: list[str] = []

    def flush() -> None:
        nonlocal current_speaker, current_role, current_label, current_text
        text_value = normalize_text(" ".join(current_text))
        if text_value:
            utterances.append(Utterance(speaker=current_speaker or current_label or "Unknown", role=current_role or "Prosecutor", text=text_value, label=current_label))
        current_speaker = ""
        current_role = ""
        current_label = ""
        current_text = []

    for line in lines:
        if not line or PAGE_RE.match(line):
            continue
        cleaned = line.upper().replace(" ", "")
        if cleaned == "PROCEEDINGS":
            continue
        match = SPEAKER_LABEL_RE.match(line)
        qa = QA_RE.match(line)
        if match or qa:
            flush()
            if match:
                current_label = normalize_text(match.group("label"))
                current_speaker = current_label
                current_role = _classify_role(current_label, appearance_map, fallback_role="Prosecutor")
                remainder = normalize_text(match.group("text"))
                if remainder:
                    current_text.append(remainder)
                continue
            current_label = qa.group("label").upper()
            current_speaker = "Question" if current_label == "Q" else "Answer"
            current_role = "Witness" if current_label == "A" else "Prosecutor"
            remainder = normalize_text(qa.group("text"))
            if remainder:
                current_text.append(remainder)
            continue
        if current_text:
            current_text.append(line)

    flush()

    cleaned: list[Utterance] = []
    for utt in utterances:
        if not utt.text:
            continue
        if utt.role not in {"Witness", "Judge", "Prosecutor", "Defence"}:
            utt.role = "Prosecutor"
        cleaned.append(utt)
    if cleaned:
        return cleaned
    # Fallback to a minimal single-utterance transcript when parsing fails.
    fallback = normalize_text(body)
    return [Utterance(speaker="Unknown", role="Prosecutor", text=fallback, label="")]


def _extract_words_from_segments(segments: Iterable[object]) -> list[TokenWord]:
    words: list[TokenWord] = []
    for segment in segments:
        seg_words = getattr(segment, "words", None) or []
        for word in seg_words:
            token_text = normalize_text(getattr(word, "word", ""))
            if not token_text:
                continue
            token = _normalize_token(token_text)
            if not token:
                continue
            start = float(getattr(word, "start", 0.0) or 0.0)
            end = float(getattr(word, "end", start) or start)
            if end < start:
                end = start
            words.append(TokenWord(token=token, start=start, end=end))
    return words


def _load_whisperx_module():
    try:
        import whisperx  # type: ignore

        return whisperx
    except Exception:
        return None


def _transcribe_with_faster_whisper(audio_path: Path, model_name: str) -> tuple[list[TokenWord], float, str]:
    if WhisperModel is None:
        raise RuntimeError("faster_whisper is not installed")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        language="en",
        word_timestamps=True,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    words = _extract_words_from_segments(segments)
    audio_duration = float(getattr(info, "duration", 0.0) or (words[-1].end if words else 0.0))
    return words, audio_duration, "faster_whisper"


def _transcribe_with_whisperx(audio_path: Path, model_name: str) -> tuple[list[TokenWord], float, str]:
    whisperx = _load_whisperx_module()
    if whisperx is None:
        raise RuntimeError("whisperx is not installed")

    audio = whisperx.load_audio(str(audio_path))
    model = whisperx.load_model(model_name, device="cpu", compute_type="int8", language="en")
    result = model.transcribe(audio, batch_size=16)
    language_code = normalize_text(result.get("language") or "en") or "en"
    align_model, metadata = whisperx.load_align_model(language_code=language_code, device="cpu")
    aligned = whisperx.align(
        result.get("segments") or [],
        align_model,
        metadata,
        audio,
        "cpu",
        return_char_alignments=False,
    )

    words: list[TokenWord] = []
    for segment in aligned.get("segments") or []:
        for word in segment.get("words") or []:
            token_text = normalize_text(word.get("word", ""))
            if not token_text:
                continue
            token = _normalize_token(token_text)
            if not token:
                continue
            start = float(word.get("start") or 0.0)
            end = float(word.get("end") or start)
            if end < start:
                end = start
            words.append(TokenWord(token=token, start=start, end=end))

    audio_duration = float(words[-1].end if words else 0.0)
    if not audio_duration and aligned.get("segments"):
        audio_duration = float(aligned["segments"][-1].get("end") or 0.0)
    return words, audio_duration, "whisperx"


def _transcribe_audio(audio_path: Path, model_name: str, backend: str) -> tuple[list[TokenWord], float, str]:
    backend = normalize_text(backend).lower() or "auto"
    if backend not in {"auto", "whisperx", "heuristic"}:
        raise ValueError(f"Unsupported alignment backend: {backend}")
    whisperx_available = _load_whisperx_module() is not None
    if backend == "whisperx" or (backend == "auto" and whisperx_available):
        try:
            return _transcribe_with_whisperx(audio_path, model_name)
        except Exception as exc:
            if backend == "whisperx":
                raise
            print(f"[phase2] whisperx failed ({exc}); falling back to faster_whisper heuristic alignment.", file=sys.stderr)
    return _transcribe_with_faster_whisper(audio_path, model_name)


def _find_exact_subsequence(haystack: list[str], needle: list[str], start: int = 0, end: int | None = None) -> int:
    if not needle or not haystack:
        return -1
    end = len(haystack) if end is None else min(end, len(haystack))
    needle_len = len(needle)
    if needle_len > end - start:
        return -1
    for idx in range(start, end - needle_len + 1):
        if haystack[idx : idx + needle_len] == needle:
            return idx
    return -1


def _alignment_payload(
    *,
    idx: int,
    start_time: float,
    end_time: float,
    alignment_status: str,
    alignment_score: float,
    alignment_method: str,
    alignment_confidence: str,
    utt_text: str,
    asr_words: list[TokenWord],
    start_idx: int | None = None,
    end_idx: int | None = None,
) -> dict[str, object]:
    if start_idx is not None and end_idx is not None and end_idx > start_idx:
        asr_text = normalize_text(" ".join(word.token for word in asr_words[start_idx:end_idx]))
        word_timestamp_count = max(0, end_idx - start_idx)
    else:
        asr_text = ""
        word_timestamp_count = 0
    transcript_text_normalized = normalize_text(utt_text)
    text_similarity = SequenceMatcher(a=_tokenize(transcript_text_normalized), b=_tokenize(asr_text)).ratio() if asr_text else 0.0
    return {
        "utterance_index": idx,
        "start_time": start_time,
        "end_time": end_time,
        "alignment_status": alignment_status,
        "alignment_score": round(float(alignment_score), 3),
        "alignment_method": alignment_method,
        "alignment_confidence": alignment_confidence,
        "asr_text": asr_text,
        "transcript_text_normalized": transcript_text_normalized,
        "text_similarity": round(float(text_similarity), 3),
        "word_timestamp_count": word_timestamp_count,
    }


def _alignment_confidence_for(
    *,
    alignment_status: str,
    alignment_score: float,
    text_similarity: float,
) -> str:
    if alignment_status == "matched":
        if alignment_score >= HIGH_CONFIDENCE_ALIGNMENT_SCORE and text_similarity >= HIGH_CONFIDENCE_TEXT_SIMILARITY:
            return "HIGH"
        if alignment_score >= MEDIUM_CONFIDENCE_ALIGNMENT_SCORE and text_similarity >= MEDIUM_CONFIDENCE_TEXT_SIMILARITY:
            return "MEDIUM"
        return "LOW"
    if alignment_status == "fuzzy":
        if alignment_score >= MEDIUM_CONFIDENCE_ALIGNMENT_SCORE and text_similarity >= MEDIUM_CONFIDENCE_TEXT_SIMILARITY:
            return "MEDIUM"
        return "LOW"
    return "LOW"


def _align_utterances(utterances: list[Utterance], words: list[TokenWord], audio_duration: float) -> list[dict[str, object]]:
    if not utterances:
        return []
    if not words:
        out: list[dict[str, object]] = []
        total_tokens = sum(max(1, len(_tokenize(utt.text))) for utt in utterances)
        cursor = 0.0
        for idx, utt in enumerate(utterances, start=1):
            token_count = max(1, len(_tokenize(utt.text)))
            span = audio_duration * (token_count / total_tokens) if total_tokens > 0 else audio_duration / max(len(utterances), 1)
            start = cursor
            end = min(audio_duration, start + span)
            if end <= start:
                end = min(audio_duration, start + 0.25)
            cursor = end
            out.append(
                {
                    **_alignment_payload(
                        idx=idx,
                        start_time=start,
                        end_time=end,
                        alignment_status="fallback",
                        alignment_score=0.0,
                        alignment_method="proportional_fallback",
                        alignment_confidence="LOW",
                        utt_text=utt.text,
                        asr_words=[],
                    ),
                }
            )
        return out

    asr_tokens = [w.token for w in words]
    total_tokens = sum(max(1, len(_tokenize(utt.text))) for utt in utterances)
    proportional_spans: list[tuple[float, float]] = []
    cumulative = 0
    for utt in utterances:
        token_count = max(1, len(_tokenize(utt.text)))
        start = audio_duration * (cumulative / total_tokens) if total_tokens else 0.0
        cumulative += token_count
        end = audio_duration * (cumulative / total_tokens) if total_tokens else audio_duration
        proportional_spans.append((start, end))

    aligned: list[dict[str, object]] = []
    cursor = 0
    for idx, (utt, fallback_span) in enumerate(zip(utterances, proportional_spans), start=1):
        tokens = _tokenize(utt.text)
        significant = _significant_tokens(tokens)
        if not tokens:
            start, end = fallback_span
            aligned.append(
                {
                    **_alignment_payload(
                        idx=idx,
                        start_time=start,
                        end_time=max(end, start + 0.25),
                        alignment_status="fallback",
                        alignment_score=0.0,
                        alignment_method="proportional_fallback",
                        alignment_confidence="LOW",
                        utt_text=utt.text,
                        asr_words=[],
                    ),
                }
            )
            continue

        expected_start = fallback_span[0]
        expected_end = fallback_span[1]
        approx_start_idx = cursor
        approx_end_idx = len(words)
        if words:
            lower = expected_start - 12.0
            upper = expected_end + 12.0
            window_indices = [i for i, word in enumerate(words) if lower <= word.start <= upper]
            if window_indices:
                approx_start_idx = max(cursor, window_indices[0])
                approx_end_idx = min(len(words), window_indices[-1] + 1)
            else:
                approx_start_idx = cursor
                approx_end_idx = min(len(words), cursor + max(80, len(tokens) * 6))

        window_tokens = asr_tokens[approx_start_idx:approx_end_idx]
        if not window_tokens:
            start, end = fallback_span
            aligned.append(
                {
                    "utterance_index": idx,
                    "start_time": start,
                    "end_time": max(end, start + 0.25),
                    "alignment_status": "fallback",
                    "alignment_score": 0.0,
                }
            )
            continue

        exact_start = -1
        if len(significant) >= 2:
            exact_start = _find_exact_subsequence(window_tokens, significant[: min(4, len(significant))], 0, len(window_tokens))
        if exact_start < 0 and len(tokens) >= 3:
            exact_start = _find_exact_subsequence(window_tokens, tokens[:3], 0, len(window_tokens))

        if exact_start >= 0:
            start_idx = approx_start_idx + exact_start
            end_idx = start_idx + len(tokens)
            if end_idx > len(words):
                end_idx = len(words)
            # Expand until the tail tokens line up or the local window ends.
            local_window = words[start_idx : min(len(words), start_idx + max(40, len(tokens) * 4))]
            local_tokens = [w.token for w in local_window]
            sm = SequenceMatcher(a=tokens, b=local_tokens)
            blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
            if blocks:
                start_offset = min(b.b for b in blocks)
                end_offset = max(b.b + b.size for b in blocks)
                start_idx = start_idx + start_offset
                end_idx = start_idx + max(1, end_offset - start_offset)
            start_time = words[start_idx].start
            end_time = words[min(end_idx - 1, len(words) - 1)].end
            score = min(1.0, sum(b.size for b in blocks) / max(1, len(tokens))) if blocks else 0.5
            aligned.append(
                {
                    **_alignment_payload(
                        idx=idx,
                        start_time=start_time,
                        end_time=max(end_time, start_time + 0.2),
                        alignment_status="matched",
                        alignment_score=score,
                        alignment_method="asr_exact",
                        alignment_confidence="HIGH",
                        utt_text=utt.text,
                        asr_words=words,
                        start_idx=start_idx,
                        end_idx=end_idx,
                    ),
                }
            )
            aligned[-1]["alignment_confidence"] = _alignment_confidence_for(
                alignment_status="matched",
                alignment_score=float(aligned[-1]["alignment_score"] or 0.0),
                text_similarity=float(aligned[-1]["text_similarity"] or 0.0),
            )
            cursor = max(cursor, end_idx)
            continue

        # Fuzzy alignment over the local window.
        sm = SequenceMatcher(a=tokens, b=window_tokens)
        blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
        if blocks:
            start_offset = min(b.b for b in blocks)
            end_offset = max(b.b + b.size for b in blocks)
            start_idx = approx_start_idx + start_offset
            end_idx = approx_start_idx + end_offset
            if end_idx <= start_idx:
                end_idx = min(len(words), start_idx + max(1, len(tokens)))
            start_time = words[start_idx].start
            end_time = words[min(end_idx - 1, len(words) - 1)].end
            score = sum(b.size for b in blocks) / max(1, len(tokens))
            aligned.append(
                {
                    **_alignment_payload(
                        idx=idx,
                        start_time=start_time,
                        end_time=max(end_time, start_time + 0.2),
                        alignment_status="fuzzy",
                        alignment_score=min(1.0, score),
                        alignment_method="asr_fuzzy",
                        alignment_confidence="MEDIUM",
                        utt_text=utt.text,
                        asr_words=words,
                        start_idx=start_idx,
                        end_idx=end_idx,
                    ),
                }
            )
            aligned[-1]["alignment_confidence"] = _alignment_confidence_for(
                alignment_status="fuzzy",
                alignment_score=float(aligned[-1]["alignment_score"] or 0.0),
                text_similarity=float(aligned[-1]["text_similarity"] or 0.0),
            )
            cursor = max(cursor, end_idx)
            continue

        start, end = fallback_span
        aligned.append(
            {
                **_alignment_payload(
                    idx=idx,
                    start_time=start,
                    end_time=max(end, start + 0.25),
                    alignment_status="fallback",
                    alignment_score=0.0,
                    alignment_method="proportional_fallback",
                    alignment_confidence="LOW",
                    utt_text=utt.text,
                    asr_words=[],
                ),
            }
        )
    return aligned


def _fmt_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _extract_segment(src: Path, dest: Path, start: float, end: float, *, video: bool) -> None:
    ensure_dir(dest.parent)
    ffmpeg = ffmpeg_exe()
    duration = max(0.05, end - start)
    cmd = [ffmpeg, "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src)]
    if video:
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"])
    else:
        cmd.extend(["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"])
    cmd.append(str(dest))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _selection_score(row: dict[str, str]) -> float:
    score = 0.0
    if normalize_text(row.get("selected_for_download")).upper() == "YES":
        score += 50.0
    if normalize_text(row.get("witness_name_or_code")) and normalize_text(row.get("witness_name_or_code")) != "UNRESOLVED_WITNESS":
        score += 20.0
    if normalize_text(row.get("selection_priority")).upper() == "HIGH":
        score += 10.0
    if normalize_text(row.get("selection_priority")).upper() == "MEDIUM":
        score += 5.0
    try:
        score += float(row.get("selection_score") or 0.0) / 10.0
    except Exception:
        pass
    return score


def _hearing_identity_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        normalize_case_number(row.get("case_number")),
        normalize_text(row.get("hearing_date")),
        normalize_text(row.get("hearing_id")),
    )


def _resolve_hearing_rows(
    hearing_rows: list[dict[str, str]],
    media_rows: list[dict[str, str]],
    selection_rows: list[dict[str, str]],
    *,
    include_hearing_ids: set[str] | None = None,
    max_hearings: int = 0,
) -> list[dict[str, str]]:
    media_by_case_date: dict[tuple[str, str], dict[str, str]] = {}
    media_by_case: dict[str, dict[str, str]] = {}
    for row in media_rows:
        case_number = normalize_case_number(row.get("resolved_case_number") or row.get("case_number"))
        date = normalize_text(row.get("chosen_date") or row.get("hearing_date"))
        if case_number and date:
            media_by_case_date[(case_number, date)] = row
        if case_number:
            media_by_case[case_number] = row

    selection_by_hearing_id: dict[str, dict[str, str]] = {}
    for row in selection_rows:
        hearing_id = normalize_text(row.get("hearing_id"))
        if hearing_id and hearing_id not in selection_by_hearing_id:
            selection_by_hearing_id[hearing_id] = row

    candidates: list[dict[str, str]] = []
    resolved: list[dict[str, str]] = []
    for row in hearing_rows:
        if normalize_text(row.get("pairing_status")).lower() != "paired":
            continue
        transcript_path = normalize_text(row.get("local_transcript_path"))
        case_number = normalize_case_number(row.get("case_number"))
        hearing_date = normalize_text(row.get("hearing_date"))
        media = media_by_case_date.get((case_number, hearing_date)) or media_by_case.get(case_number)
        if include_hearing_ids and normalize_text(row.get("hearing_id")) in include_hearing_ids:
            selection_row = selection_by_hearing_id.get(normalize_text(row.get("hearing_id")), {})
            candidates.append(
                {
                    **row,
                    "_media_video_path": normalize_text((media or {}).get("local_video_path", "")),
                    "_selection_score": str(1000.0 + _selection_score(selection_row)),
                    "_selection_witness_name_or_code": normalize_text(selection_row.get("witness_name_or_code")),
                    "_selection_examination_type": normalize_text(selection_row.get("examination_type")),
                }
            )
            continue
        score = _selection_score(selection_by_hearing_id.get(normalize_text(row.get("hearing_id")), {}))
        selection_row = selection_by_hearing_id.get(normalize_text(row.get("hearing_id")), {})
        if transcript_path or normalize_text(row.get("transcript_url")):
            candidates.append(
                {
                    **row,
                    "_media_video_path": normalize_text((media or {}).get("local_video_path", "")),
                    "_selection_score": str(score),
                    "_selection_witness_name_or_code": normalize_text(selection_row.get("witness_name_or_code")),
                    "_selection_examination_type": normalize_text(selection_row.get("examination_type")),
                }
            )

    candidates.sort(
        key=lambda row: (
            -float(row.get("_selection_score") or 0.0),
            0 if normalize_text(row.get("witness_name_or_code")) and normalize_text(row.get("witness_name_or_code")) != "UNRESOLVED_WITNESS" else 1,
            normalize_case_number(row.get("case_number")),
            normalize_text(row.get("hearing_date")),
            normalize_text(row.get("hearing_id")),
        )
    )

    seen_hearing_ids: set[str] = set()
    for row in candidates:
        hearing_id = normalize_text(row.get("hearing_id"))
        if not hearing_id or hearing_id in seen_hearing_ids:
            continue
        seen_hearing_ids.add(hearing_id)
        resolved.append(row)
        if max_hearings > 0 and len(resolved) >= max_hearings:
            break
    return resolved


def _load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return read_csv_rows(path)


def _resolve_existing_file(path_text: str) -> Path | None:
    text = normalize_text(path_text)
    if not text or text == ".":
        return None
    path = Path(text)
    if not path.exists() or not path.is_file():
        return None
    return path


def _load_source_offsets(path: Path) -> dict[str, float]:
    offsets: dict[str, float] = {}
    for row in _load_rows(path):
        hearing_id = normalize_text(row.get("hearing_id"))
        if not hearing_id:
            continue
        try:
            offsets[hearing_id] = max(0.0, float(row.get("source_offset_seconds") or 0.0))
        except Exception:
            continue
    return offsets


def _speaker_name_or_code(row: dict[str, str]) -> str:
    value = normalize_text(row.get("witness_name_or_code"))
    return value or "UNRESOLVED_WITNESS"


def _download_if_needed(url: str, dest: Path, *, skip_existing: bool = True) -> Path:
    if not url:
        raise ValueError("missing URL")
    if skip_existing and dest.exists() and dest.stat().st_size > 0:
        return dest
    ensure_dir(dest.parent)
    return download_file(url, dest, timeout=600)


def _probe_local_media(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "media_validation_status": "missing",
            "probed_duration_seconds": 0.0,
            "video_playable": False,
            "audio_present": False,
            "video_codec": "",
            "audio_codec": "",
            "resolution": "",
            "frame_rate": "",
        }
    probe = probe_media_url(str(path))
    return {
        "media_validation_status": probe.status,
        "probed_duration_seconds": probe.duration_seconds,
        "video_playable": probe.video_playable,
        "audio_present": probe.audio_present,
        "video_codec": probe.video_codec,
        "audio_codec": probe.audio_codec,
        "resolution": probe.resolution,
        "frame_rate": probe.frame_rate,
    }


def _audio_metrics(path: Path) -> dict[str, object]:
    if not path.exists() or path.stat().st_size == 0:
        return {
            "audio_present": "NO",
            "audio_rms": 0.0,
            "silence_ratio": 1.0,
            "clipping_ratio": 1.0,
            "sample_rate": 0,
            "audio_validation_status": "missing",
        }
    try:
        with wave.open(str(path), "rb") as wf:
            sample_rate = wf.getframerate()
            nframes = wf.getnframes()
            frames = wf.readframes(nframes)
            sampwidth = wf.getsampwidth()
            channels = wf.getnchannels()
        if sampwidth != 2:
            return {
                "audio_present": "YES",
                "audio_rms": 0.0,
                "silence_ratio": 0.0,
                "clipping_ratio": 0.0,
                "sample_rate": sample_rate,
                "audio_validation_status": "unsupported_format",
            }
        rms = audioop.rms(frames, sampwidth) / 32768.0 if frames else 0.0
        max_amp = 32767
        ints = memoryview(frames).cast("h") if frames else []
        total = len(ints) if frames else 0
        silent = 0
        clipped = 0
        for sample in ints:
            abs_sample = abs(int(sample))
            if abs_sample <= int(max_amp * 0.01):
                silent += 1
            if abs_sample >= int(max_amp * 0.98):
                clipped += 1
        silence_ratio = silent / total if total else 1.0
        clipping_ratio = clipped / total if total else 1.0
        if total == 0 or sample_rate <= 0:
            status = "invalid"
        elif silence_ratio > 0.98:
            status = "silent"
        elif clipping_ratio > 0.1:
            status = "clipped"
        else:
            status = "valid"
        return {
            "audio_present": "YES",
            "audio_rms": round(float(rms), 6),
            "silence_ratio": round(float(silence_ratio), 6),
            "clipping_ratio": round(float(clipping_ratio), 6),
            "sample_rate": sample_rate,
            "audio_validation_status": status,
        }
    except Exception:
        return {
            "audio_present": "NO",
            "audio_rms": 0.0,
            "silence_ratio": 1.0,
            "clipping_ratio": 1.0,
            "sample_rate": 0,
            "audio_validation_status": "corrupt",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a MELD-style utterance-level dataset from aligned legal hearings")
    parser.add_argument("--hearing-manifest", default=str(HEARING_MANIFEST))
    parser.add_argument("--media-manifest", default=str(MEDIA_MANIFEST))
    parser.add_argument("--selection-manifest", default=str(SELECTION_MANIFEST))
    parser.add_argument("--source-offsets-csv", default=str(SOURCE_OFFSET_MANIFEST), help="Optional hearing_id to source offset mapping CSV")
    parser.add_argument("--include-hearing-ids", default="", help="Comma-separated hearing IDs that must be included")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    parser.add_argument("--model-name", default="tiny.en")
    parser.add_argument("--max-hearings", type=int, default=0, help="Limit the number of hearings processed for a pilot run")
    parser.add_argument("--max-utterances", type=int, default=0, help="Limit utterances exported per hearing for a pilot run")
    parser.add_argument("--start-padding-ms", type=int, default=350, help="Padding applied before each utterance clip")
    parser.add_argument("--end-padding-ms", type=int, default=550, help="Padding applied after each utterance clip")
    parser.add_argument("--min-clip-seconds", type=float, default=0.8, help="Minimum exported clip length")
    parser.add_argument("--max-clip-seconds", type=float, default=30.0, help="Maximum exported clip length")
    parser.add_argument("--skip-existing", action="store_true", help="Skip regenerated clip files when they already exist")
    parser.add_argument(
        "--alignment-backend",
        default="auto",
        choices=["auto", "whisperx", "heuristic"],
        help="Alignment backend: auto prefers whisperx when installed, whisperx requires whisperx, heuristic keeps the current faster_whisper path.",
    )
    args = parser.parse_args()

    hearing_rows = _load_rows(Path(args.hearing_manifest))
    media_rows = _load_rows(Path(args.media_manifest))
    selection_rows = _load_rows(Path(args.selection_manifest))
    source_offsets = _load_source_offsets(Path(args.source_offsets_csv))
    include_hearing_ids = {item.strip() for item in normalize_text(args.include_hearing_ids).split(",") if item.strip()}
    resolved_rows = _resolve_hearing_rows(
        hearing_rows,
        media_rows,
        selection_rows,
        include_hearing_ids=include_hearing_ids,
        max_hearings=args.max_hearings,
    )
    if not resolved_rows:
        raise SystemExit("No paired hearings with usable transcript/video metadata were resolved.")

    out_root = Path(args.output_root)
    clips_root = ensure_dir(out_root / "clips")
    audio_root = ensure_dir(out_root / "audio")
    transcripts_root = ensure_dir(out_root / "transcripts")
    labels_root = ensure_dir(out_root / "labels")
    cache_root = ensure_dir(out_root / "cache")

    metadata_rows: list[dict[str, object]] = []
    hearing_counts: dict[str, int] = {}
    summary = {
        "hearings_resolved": len(resolved_rows),
        "utterances_parsed": 0,
        "utterances_exported": 0,
        "matched_alignments": 0,
        "fuzzy_alignments": 0,
        "fallback_alignments": 0,
        "cases_represented": 0,
        "case_counts": {},
        "speaker_role_counts": Counter(),
        "split_counts": Counter(),
        "quality_tier_counts": Counter(),
        "alignment_confidence_counts": Counter(),
        "manual_review_count": 0,
        "audio_valid_count": 0,
        "video_valid_count": 0,
        "witness_visible_count": 0,
        "split_leakage_violations": 0,
        "source_offset_seconds": {},
        "model_name": args.model_name,
        "alignment_backend": args.alignment_backend,
        "output_root": str(out_root),
    }

    for hearing in resolved_rows:
        hearing_id = normalize_text(hearing.get("hearing_id"))
        case_number = normalize_case_number(hearing.get("case_number"))
        hearing_date = normalize_text(hearing.get("hearing_date"))
        tribunal = normalize_text(hearing.get("tribunal"))
        case_family = normalize_text(hearing.get("case_family"))
        transcript_url = normalize_text(hearing.get("transcript_url"))
        video_url = normalize_text(hearing.get("video_url"))
        source_witness = normalize_text(hearing.get("_selection_witness_name_or_code")) or _speaker_name_or_code(hearing)
        source_examination = normalize_text(hearing.get("_selection_examination_type")) or normalize_text(hearing.get("examination_type")) or "unknown"
        source_offset_seconds = float(source_offsets.get(hearing_id, 0.0))
        summary["source_offset_seconds"][hearing_id] = round(source_offset_seconds, 3)

        transcript_source_text = normalize_text(hearing.get("local_transcript_path"))
        transcript_source_path = Path(transcript_source_text) if transcript_source_text else Path("")
        if (not transcript_source_text or not transcript_source_path.exists()) and transcript_url:
            transcript_source_path = maybe_download_transcript(transcript_url, hearing_id, output_dir=transcripts_root)
        if not transcript_source_path.exists():
            continue

        video_source_text = normalize_text(hearing.get("_media_video_path"))
        video_source_path = _resolve_existing_file(video_source_text)
        if video_source_path is None and video_url:
            suffix = Path(video_url.split("?")[0]).suffix.lower() or ".mp4"
            if suffix not in {".mp4", ".mov", ".mkv", ".m4v", ".webm"}:
                suffix = ".mp4"
            video_dest = ensure_dir(out_root / "source_videos") / f"{hearing_id}{suffix}"
            try:
                video_source_path = _download_if_needed(video_url, video_dest, skip_existing=args.skip_existing)
            except Exception:
                video_source_path = None
        if video_source_path is None or not video_source_path.exists():
            continue

        source_probe = _probe_local_media(video_source_path)
        transcript_text, _page_count = extract_transcript_text(transcript_source_path)
        transcript_copy = transcripts_root / f"{hearing_id}.txt"
        if not transcript_copy.exists() or transcript_copy.read_text(encoding="utf-8", errors="ignore") != transcript_text:
            transcript_copy.write_text(transcript_text, encoding="utf-8")

        utterances = segment_transcript(
            transcript_text,
            witness_id=_speaker_name_or_code(hearing),
            default_examination_type=normalize_text(hearing.get("examination_type")) or "unknown",
        )
        if args.max_utterances > 0:
            utterances = utterances[: args.max_utterances]
        summary["utterances_parsed"] += len(utterances)

        hearing_audio = cache_root / "audio" / f"{hearing_id}.wav"
        if not hearing_audio.exists() or hearing_audio.stat().st_size == 0:
            source_duration = float(source_probe.get("probed_duration_seconds") or 0.0) or 0.0
            if source_duration > source_offset_seconds:
                _extract_segment(
                    video_source_path,
                    hearing_audio,
                    source_offset_seconds,
                    source_duration,
                    video=False,
                )
            else:
                _extract_segment(video_source_path, hearing_audio, 0.0, max(1.0, source_duration or 1.0), video=False)

        words, audio_duration, transcript_backend = _transcribe_audio(hearing_audio, args.model_name, args.alignment_backend)
        summary["transcript_backend"] = transcript_backend

        alignment = _align_utterances(utterances, words, audio_duration)
        hearing_dir_clip = ensure_dir(clips_root / hearing_id)
        hearing_dir_audio = ensure_dir(audio_root / hearing_id)
        speaker_role_counts = Counter()
        selection_witness = source_witness if source_witness and source_witness != "UNRESOLVED_WITNESS" else "UNRESOLVED_WITNESS"

        for idx, (utt, aligned) in enumerate(zip(utterances, alignment), start=1):
            start = float(aligned["start_time"]) + source_offset_seconds
            end = float(aligned["end_time"]) + source_offset_seconds
            if end <= start:
                end = start + 0.25
            start = max(0.0, start - (args.start_padding_ms / 1000.0))
            end = end + (args.end_padding_ms / 1000.0)
            if source_probe.get("probed_duration_seconds"):
                end = min(float(source_probe.get("probed_duration_seconds") or 0.0), end)
            if end - start < args.min_clip_seconds:
                end = start + args.min_clip_seconds
            if end - start > args.max_clip_seconds:
                end = start + args.max_clip_seconds
            if source_probe.get("probed_duration_seconds"):
                end = min(float(source_probe.get("probed_duration_seconds") or 0.0), end)
            if end <= start:
                end = start + max(args.min_clip_seconds, 0.25)
            utterance_id = f"{hearing_id}_utt{idx:05d}"
            clip_name = f"utt{idx:05d}.mp4"
            audio_name = f"utt{idx:05d}.wav"
            rel_video = f"clips/{hearing_id}/{clip_name}"
            rel_audio = f"audio/{hearing_id}/{audio_name}"
            video_dest = hearing_dir_clip / clip_name
            audio_dest = hearing_dir_audio / audio_name
            if not (args.skip_existing and video_dest.exists() and audio_dest.exists()):
                _extract_segment(video_source_path, video_dest, start, end, video=True)
                _extract_segment(video_source_path, audio_dest, start, end, video=False)

            duration_ms = int(round((end - start) * 1000))
            role = utt.role
            speaker_role_counts[role] += 1
            summary["speaker_role_counts"][role] += 1
            alignment_status = str(aligned["alignment_status"])
            summary[f"{alignment_status}_alignments"] = int(summary.get(f"{alignment_status}_alignments", 0)) + 1
            utterance_text = utt.text
            witness_id = selection_witness
            clip_probe = _probe_local_media(video_dest)
            audio_metrics = _audio_metrics(audio_dest)
            alignment_confidence = normalize_text(aligned.get("alignment_confidence")).upper() or (
                "HIGH" if alignment_status == "matched" else "MEDIUM" if alignment_status == "fuzzy" else "LOW"
            )
            clip_duration_seconds = round(max(0.0, end - start), 3)
            transcript_text_normalized = normalize_text(aligned.get("transcript_text_normalized") or utterance_text)
            asr_text = normalize_text(aligned.get("asr_text"))
            text_similarity = float(aligned.get("text_similarity") or 0.0)
            word_timestamp_count = int(aligned.get("word_timestamp_count") or 0)
            manual_review_required = (
                "YES"
                if alignment_confidence == "LOW"
                or text_similarity < REVIEW_TEXT_SIMILARITY
                or audio_metrics["audio_validation_status"] != "valid"
                or clip_probe.get("media_validation_status") != "validated"
                else "NO"
            )
            if clip_duration_seconds > args.max_clip_seconds or clip_duration_seconds < args.min_clip_seconds:
                manual_review_required = "YES"

            video_quality_status = "VALID" if clip_probe.get("media_validation_status") == "validated" else str(clip_probe.get("media_validation_status") or "unknown").upper()
            face_detected = "UNKNOWN"
            face_visible_ratio = ""
            shot_type = "UNKNOWN"
            speaker_visible = "UNKNOWN"
            if video_quality_status == "VALID" and role == "Witness" and alignment_confidence == "HIGH" and audio_metrics["audio_validation_status"] == "valid":
                speaker_visible = "UNKNOWN"
                summary["witness_visible_count"] += 0

            quality_tier = "REJECT"
            if audio_metrics["audio_validation_status"] == "valid" and clip_probe.get("media_validation_status") == "validated":
                if alignment_confidence == "HIGH" and manual_review_required == "NO":
                    quality_tier = "B"
                elif alignment_confidence in {"HIGH", "MEDIUM"}:
                    quality_tier = "B"
                elif alignment_confidence == "LOW":
                    quality_tier = "C"
            if (
                alignment_status == "fallback"
                or audio_metrics["audio_validation_status"] in {"silent", "clipped", "corrupt", "missing"}
                or text_similarity < REVIEW_TEXT_SIMILARITY
            ):
                quality_tier = "REJECT"

            split_group_id = selection_witness if selection_witness != "UNRESOLVED_WITNESS" else hearing_id
            split_strategy = "witness_disjoint" if selection_witness != "UNRESOLVED_WITNESS" else "hearing_disjoint"
            row = {
                "utterance_id": utterance_id,
                "hearing_id": hearing_id,
                "tribunal": tribunal,
                "case_number": case_number,
                "case_family": case_family,
                "hearing_date": hearing_date,
                "source_offset_seconds": round(source_offset_seconds, 3),
                "witness_id": witness_id,
                "speaker_role": role,
                "speaker_name": utt.speaker,
                "examination_type": source_examination,
                "utterance_text": utterance_text,
                "start_time": _fmt_time(start),
                "end_time": _fmt_time(end),
                "duration_ms": duration_ms,
                "video_clip": rel_video,
                "audio_clip": rel_audio,
                "transcript_source": f"transcripts/{hearing_id}.txt",
                "alignment_status": alignment_status,
                "alignment_score": aligned["alignment_score"],
                "alignment_method": aligned.get("alignment_method", ""),
                "alignment_confidence": alignment_confidence,
                "asr_text": asr_text,
                "transcript_text_normalized": transcript_text_normalized,
                "text_similarity": text_similarity,
                "clip_duration_seconds": clip_duration_seconds,
                "word_timestamp_count": word_timestamp_count,
                "manual_review_required": manual_review_required,
                "split_group_id": split_group_id,
                "split_strategy": split_strategy,
                "quality_tier": quality_tier,
                "audio_present": audio_metrics["audio_present"],
                "audio_rms": audio_metrics["audio_rms"],
                "silence_ratio": audio_metrics["silence_ratio"],
                "clipping_ratio": audio_metrics["clipping_ratio"],
                "sample_rate": audio_metrics["sample_rate"],
                "audio_validation_status": audio_metrics["audio_validation_status"],
                "face_detected": face_detected,
                "face_visible_ratio": face_visible_ratio,
                "shot_type": shot_type,
                "speaker_visible": speaker_visible,
                "video_quality_status": video_quality_status,
                "emotion": "",
                "credibility": "",
                "split": "",
            }
            metadata_rows.append(row)
            summary["utterances_exported"] += 1
            summary["alignment_confidence_counts"][alignment_confidence] += 1
            summary["quality_tier_counts"][quality_tier] += 1
            if manual_review_required == "YES":
                summary["manual_review_count"] += 1
            if audio_metrics["audio_validation_status"] == "valid":
                summary["audio_valid_count"] += 1
            if clip_probe.get("media_validation_status") == "validated":
                summary["video_valid_count"] += 1
            if speaker_visible == "YES":
                summary["witness_visible_count"] += 1

        hearing_counts[hearing_id] = len(utterances)

    if not metadata_rows:
        raise SystemExit("No utterance rows were produced.")

    eligible_rows = [row for row in metadata_rows if row.get("quality_tier") in {"A", "B"}]
    eligible_group_ids = [str(row.get("split_group_id") or row.get("hearing_id") or "") for row in eligible_rows if str(row.get("split_group_id") or row.get("hearing_id") or "").strip()]
    split_group_map = group_case_splits(
        eligible_group_ids,
        train_ratio=0.7,
        dev_ratio=0.15,
        test_ratio=0.15,
        seed=42,
    )
    if len(set(eligible_group_ids)) == 1 and eligible_group_ids:
        split_group_map[eligible_group_ids[0]] = "train"

    for row in metadata_rows:
        group_id = str(row.get("split_group_id") or row.get("hearing_id") or "")
        if row.get("quality_tier") in {"A", "B"}:
            row["split"] = split_group_map.get(group_id, "train")
        else:
            row["split"] = "review"

    metadata_rows.sort(key=lambda row: (row["hearing_id"], row["start_time"], row["utterance_id"]))
    metadata_csv = out_root / "legalmeld_metadata_validated.csv"
    write_csv(metadata_csv, metadata_rows, MASTER_COLUMNS)
    legacy_metadata_csv = out_root / "legalmeld_metadata.csv"
    write_csv(legacy_metadata_csv, metadata_rows, MASTER_COLUMNS)

    # MELD-style split files.
    split_buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in metadata_rows:
        if row["split"] in {"train", "dev", "test"}:
            split_buckets[str(row["split"])].append(row)
    for split_name in ["train", "dev", "test"]:
        split_rows = split_buckets.get(split_name, [])
        meld_rows = [
            {
                "Dialogue_ID": row["hearing_id"],
                "Utterance_ID": row["utterance_id"],
                "Utterance": row["utterance_text"],
                "Speaker": row["speaker_name"],
                "SpeakerRole": row["speaker_role"],
                "WitnessID": row["witness_id"],
                "Emotion": row["emotion"],
                "Credibility": row["credibility"],
                "CaseNumber": row["case_number"],
                "CaseFamily": row["case_family"],
                "HearingDate": row["hearing_date"],
                "ExaminationType": row["examination_type"],
                "StartTime": row["start_time"],
                "EndTime": row["end_time"],
                "DurationMs": row["duration_ms"],
                "VideoPath": row["video_clip"],
                "AudioPath": row["audio_clip"],
                "TranscriptSource": row["transcript_source"],
                "SourceOffsetSeconds": row["source_offset_seconds"],
                "AlignmentStatus": row["alignment_status"],
                "AlignmentScore": row["alignment_score"],
            }
            for row in split_rows
        ]
        write_csv(out_root / f"{split_name}.csv", meld_rows, MELD_COLUMNS)

    review_rows = [
        row
        for row in metadata_rows
        if row.get("manual_review_required") == "YES" or row.get("quality_tier") in {"C", "REJECT"}
    ]
    review_rows.sort(key=lambda row: (row.get("quality_tier"), row.get("alignment_confidence"), row.get("text_similarity")), reverse=True)
    write_csv(out_root / "alignment_review_sample.csv", review_rows[:50], MASTER_COLUMNS)

    # Minimal labels directory stub for future annotation stages.
    (labels_root / "README.txt").write_text(
        "Emotion and credibility labels are intentionally left blank in Stage 3.\n"
        "Use this directory later for annotation exports and derived label files.\n",
        encoding="utf-8",
    )

    summary["cases_represented"] = len({row["case_number"] for row in metadata_rows if row["case_number"]})
    summary["case_counts"] = dict(Counter(row["case_number"] for row in metadata_rows))
    summary["speaker_role_counts"] = dict(summary["speaker_role_counts"])
    summary["split_counts"] = dict(Counter(row["split"] for row in metadata_rows if row["split"] in {"train", "dev", "test"}))
    summary["quality_tier_counts"] = dict(summary["quality_tier_counts"])
    summary["alignment_confidence_counts"] = dict(summary["alignment_confidence_counts"])
    summary["hearing_counts"] = hearing_counts
    summary["metadata_csv"] = str(metadata_csv)
    summary["legacy_metadata_csv"] = str(legacy_metadata_csv)
    summary["train_csv"] = str(out_root / "train.csv")
    summary["dev_csv"] = str(out_root / "dev.csv")
    summary["test_csv"] = str(out_root / "test.csv")
    summary["review_sample_csv"] = str(out_root / "alignment_review_sample.csv")
    summary["clips_dir"] = str(clips_root)
    summary["audio_dir"] = str(audio_root)
    summary["transcripts_dir"] = str(transcripts_root)
    summary["total_clip_hours"] = round(sum(float(row["clip_duration_seconds"] or 0) for row in metadata_rows if row.get("split") in {"train", "dev", "test"}) / 3600.0, 3)
    summary["average_clip_duration_seconds"] = round(
        sum(float(row["clip_duration_seconds"] or 0) for row in metadata_rows if row.get("split") in {"train", "dev", "test"}) / max(1, sum(1 for row in metadata_rows if row.get("split") in {"train", "dev", "test"})),
        3,
    )
    summary["distinct_witnesses"] = len({row["witness_id"] for row in metadata_rows if row.get("witness_id")})
    summary["hearings_represented"] = len({row["hearing_id"] for row in metadata_rows if row.get("hearing_id")})
    summary["split_leakage_violations"] = 0 if len({row["split_group_id"] for row in metadata_rows if row.get("split") in {"train", "dev", "test"}}) == len({(row["split_group_id"], row["split"]) for row in metadata_rows if row.get("split") in {"train", "dev", "test"}}) else 1
    summary["validated_utterances"] = sum(1 for row in metadata_rows if row.get("split") in {"train", "dev", "test"})
    summary["rejected_utterances"] = sum(1 for row in metadata_rows if row.get("quality_tier") == "REJECT")
    summary["high_confidence_alignments"] = sum(1 for row in metadata_rows if row.get("alignment_confidence") == "HIGH")
    summary["fuzzy_alignments"] = sum(1 for row in metadata_rows if row.get("alignment_confidence") == "MEDIUM")
    summary["rejected_alignments"] = sum(1 for row in metadata_rows if row.get("alignment_confidence") == "LOW")
    summary["witness_visible_clips"] = summary["witness_visible_count"]
    summary["audio_valid_clips"] = summary["audio_valid_count"]
    summary["total_utterances"] = len(metadata_rows)
    summary_path = out_root / "dataset_quality_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    legacy_summary_path = out_root / "legalmeld_dataset_summary.json"
    legacy_summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
