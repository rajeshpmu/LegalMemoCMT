#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.preprocessing import PreprocessConfig, sample_video_frames


YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_MODEL = Path.home() / ".cache" / "legalmemocmt" / "face_detection_yunet_2023mar.onnx"


def center_crop_square(frame_rgb: np.ndarray) -> np.ndarray:
    h, w = frame_rgb.shape[:2]
    side = min(h, w)
    top = max((h - side) // 2, 0)
    left = max((w - side) // 2, 0)
    crop = frame_rgb[top : top + side, left : left + side]
    if crop.size == 0:
        return frame_rgb
    return crop


def ensure_yunet_model() -> Path:
    YUNET_MODEL.parent.mkdir(parents=True, exist_ok=True)
    if not YUNET_MODEL.exists():
        urllib.request.urlretrieve(YUNET_URL, YUNET_MODEL)
    return YUNET_MODEL


def detect_face_box(frame_rgb: np.ndarray) -> tuple[tuple[int, int, int, int] | None, str]:
    """Return the largest detected face box in RGB coordinates.

    The output is (x, y, w, h) in the original frame pixel space.
    If no face is found, return None and the fallback mode name.
    """
    frame_bgr = cv2.cvtColor(np.clip(frame_rgb * 255.0, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    model_path = ensure_yunet_model()
    detector = cv2.FaceDetectorYN_create(str(model_path), "", (frame_bgr.shape[1], frame_bgr.shape[0]))
    detector.setInputSize((frame_bgr.shape[1], frame_bgr.shape[0]))
    _, faces = detector.detect(frame_bgr)
    if faces is None or len(faces) == 0:
        return None, "center_crop_fallback"
    faces = sorted(faces, key=lambda row: float(row[2]) * float(row[3]), reverse=True)
    x, y, w, h = faces[0][:4]
    return (int(round(x)), int(round(y)), int(round(w)), int(round(h))), "face_detected"


def crop_face_from_frame(
    frame_rgb: np.ndarray,
    frame_size: int,
    face_box: tuple[int, int, int, int] | None,
) -> np.ndarray:
    frame_uint8 = np.clip(frame_rgb * 255.0, 0, 255).astype(np.uint8)
    if face_box is None:
        crop = center_crop_square(frame_uint8)
    else:
        x, y, w, h = face_box
        pad_x = max(int(0.15 * w), 4)
        pad_y = max(int(0.15 * h), 4)
        x1 = max(x - pad_x, 0)
        y1 = max(y - pad_y, 0)
        x2 = min(x + w + pad_x, frame_uint8.shape[1])
        y2 = min(y + h + pad_y, frame_uint8.shape[0])
        crop = frame_uint8[y1:y2, x1:x2]
        if crop.size == 0:
            crop = center_crop_square(frame_uint8)

    crop = cv2.resize(crop, (frame_size, frame_size), interpolation=cv2.INTER_AREA)
    return crop


def draw_face_box(frame_rgb: np.ndarray, face_box: tuple[int, int, int, int] | None, label: str) -> np.ndarray:
    frame_uint8 = np.clip(frame_rgb * 255.0, 0, 255).astype(np.uint8)
    frame_bgr = cv2.cvtColor(frame_uint8, cv2.COLOR_RGB2BGR)
    if face_box is not None:
        x, y, w, h = face_box
        cv2.rectangle(frame_bgr, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.putText(
            frame_bgr,
            label,
            (max(8, x), max(24, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.putText(
            frame_bgr,
            label,
            (16, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 200, 255),
            2,
            cv2.LINE_AA,
        )
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)


def save_contact_sheet(items: list[dict[str, Any]], output_path: Path) -> None:
    if not items:
        return

    n = len(items)
    cols = 3 if n >= 3 else n
    rows = int(np.ceil(n / cols))
    cell_w = 520
    cell_h = 420
    header_h = 46
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h + header_h), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
        label_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except Exception:
        title_font = ImageFont.load_default()
        label_font = ImageFont.load_default()

    draw.text((16, 10), "MELD Face-Crop Preview", fill="black", font=title_font)

    for idx, item in enumerate(items):
        r = idx // cols
        c = idx % cols
        x0 = c * cell_w
        y0 = header_h + r * cell_h
        panel = Image.fromarray(item["annotated"]).resize((cell_w - 20, cell_h - 60))
        sheet.paste(panel, (x0 + 10, y0 + 30))
        caption = f"frame={item['frame_index']} | {item['status']} | {item['crop_mode']}"
        draw.text((x0 + 10, y0 + 6), caption, fill="black", font=label_font)

    sheet.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview which face region is cropped from a MELD clip before ViT embedding extraction."
    )
    parser.add_argument("--video-path", required=True, help="Raw MELD MP4 clip.")
    parser.add_argument("--output-dir", default="results/facecrop_preview", help="Directory for saved preview artifacts.")
    parser.add_argument("--num-frames", type=int, default=6, help="How many sampled frames to inspect.")
    parser.add_argument("--frame-size", type=int, default=224, help="Resize size used for the crop preview.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--max-audio-seconds", type=float, default=10.0)
    args = parser.parse_args()

    video_path = Path(args.video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    out_dir = Path(args.output_dir) / video_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = PreprocessConfig(frame_size=args.frame_size, num_frames=args.num_frames, sample_rate=args.sample_rate, max_audio_seconds=args.max_audio_seconds)

    frames = sample_video_frames(str(video_path), cfg)
    if frames.size == 0:
        raise RuntimeError(f"No frames sampled from {video_path}")

    report_rows = []
    preview_items: list[dict[str, Any]] = []

    for idx, frame in enumerate(frames):
        face_box, status = detect_face_box(frame)
        crop = crop_face_from_frame(frame, cfg.frame_size, face_box)
        crop_mode = "face_crop" if face_box is not None else "center_crop_fallback"
        label = f"{status} | {crop_mode}"
        annotated = draw_face_box(frame, face_box, label)

        original_path = out_dir / f"frame_{idx:02d}_original.png"
        annotated_path = out_dir / f"frame_{idx:02d}_annotated.png"
        crop_path = out_dir / f"frame_{idx:02d}_crop.png"
        cv2.imwrite(str(original_path), cv2.cvtColor(np.clip(frame * 255.0, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(annotated_path), cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(crop_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))

        report_rows.append(
            {
                "frame_index": idx,
                "status": status,
                "crop_mode": crop_mode,
                "face_box_x": "" if face_box is None else face_box[0],
                "face_box_y": "" if face_box is None else face_box[1],
                "face_box_w": "" if face_box is None else face_box[2],
                "face_box_h": "" if face_box is None else face_box[3],
                "original_path": str(original_path),
                "annotated_path": str(annotated_path),
                "crop_path": str(crop_path),
            }
        )
        preview_items.append(
            {
                "frame_index": idx,
                "status": status,
                "crop_mode": crop_mode,
                "annotated": annotated,
            }
        )

    csv_path = out_dir / "facecrop_preview_report.csv"
    json_path = out_dir / "facecrop_preview_report.json"
    sheet_path = out_dir / "facecrop_contact_sheet.png"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(report_rows)

    json_path.write_text(json.dumps(report_rows, indent=2), encoding="utf-8")
    save_contact_sheet(preview_items, sheet_path)

    print("MELD face-crop preview")
    print(f"video_path: {video_path}")
    print(f"output_dir: {out_dir}")
    print(f"frames_sampled: {len(frames)}")
    print(f"report_csv: {csv_path}")
    print(f"report_json: {json_path}")
    print(f"contact_sheet: {sheet_path}")
    print("Saved per-frame original, annotated, and crop images for inspection.")


if __name__ == "__main__":
    main()
