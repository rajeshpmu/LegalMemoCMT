from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/DejaVu Sans Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/DejaVu Sans.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _blend_white_blue(value: float) -> tuple[int, int, int]:
    value = max(0.0, min(1.0, value))
    r = int(255 * (1 - 0.2 * value))
    g = int(255 * (1 - 0.35 * value))
    b = int(255 * (1 - 0.7 * value))
    return r, g, b


def render_matrix(csv_path: Path, out_path: Path, title: str) -> None:
    df = pd.read_csv(csv_path, index_col=0)
    values = df.to_numpy(dtype=float)
    nrows, ncols = values.shape
    cell = 78
    left = 200
    top = 120
    right = 80
    bottom = 100
    width = left + ncols * cell + right
    height = top + nrows * cell + bottom

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    title_font = _font(26, bold=True)
    label_font = _font(18, bold=True)
    cell_font = _font(18, bold=False)
    small_font = _font(13, bold=False)

    draw.text((left, 25), title, fill="black", font=title_font)
    draw.text((20, top + nrows * cell // 2 - 20), "Actual", fill="black", font=label_font)
    draw.text((left + ncols * cell // 2 - 30, top + nrows * cell + 25), "Predicted", fill="black", font=label_font)

    max_value = float(values.max()) if values.size else 1.0
    if max_value <= 0:
        max_value = 1.0

    for i, idx in enumerate(df.index.tolist()):
        row_label = str(idx)
        draw.text((20, top + i * cell + cell // 2 - 10), row_label, fill="black", font=small_font)
        for j, col in enumerate(df.columns.tolist()):
            val = float(df.iloc[i, j])
            norm = val / max_value
            x0 = left + j * cell
            y0 = top + i * cell
            x1 = x0 + cell
            y1 = y0 + cell
            draw.rectangle([x0, y0, x1, y1], fill=_blend_white_blue(norm), outline="white")
            text = str(int(val))
            bbox = draw.textbbox((0, 0), text, font=cell_font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text((x0 + (cell - tw) / 2, y0 + (cell - th) / 2 - 2), text, fill="black", font=cell_font)

    for j, col in enumerate(df.columns.tolist()):
        text = str(col)
        bbox = draw.textbbox((0, 0), text, font=small_font)
        tw = bbox[2] - bbox[0]
        draw.text((left + j * cell + (cell - tw) / 2, top - 28), text, fill="black", font=small_font)

    draw.line((left, top, left + ncols * cell, top), fill="black", width=2)
    draw.line((left, top, left, top + nrows * cell), fill="black", width=2)
    draw.line((left + ncols * cell, top, left + ncols * cell, top + nrows * cell), fill="black", width=2)
    draw.line((left, top + nrows * cell, left + ncols * cell, top + nrows * cell), fill="black", width=2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render confusion matrix image from CSV")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-png", required=True)
    parser.add_argument("--title", default="Confusion Matrix")
    args = parser.parse_args()
    render_matrix(Path(args.input_csv), Path(args.output_png), args.title)
    print(f"Wrote {args.output_png}")


if __name__ == "__main__":
    main()
