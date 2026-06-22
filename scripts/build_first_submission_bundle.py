from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission_first"


ESSENTIAL_FILES = [
    "README_PHASE1.md",
    "README_PAPER_EXACT.md",
    "FIRST_SUBMISSION_CHECKLIST.md",
    "requirements-phase1.txt",
]

ESSENTIAL_DIRS = [
    "src",
]

ESSENTIAL_SCRIPT_PATTERNS = [
    "scripts/*.sh",
]

EXCLUDE_DIRS = {
    "__pycache__",
    ".DS_Store",
    "data",
    "results",
    "artifacts",
}


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    for path in src.rglob("*"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.is_dir():
            continue
        rel = path.relative_to(ROOT)
        if rel.parts and rel.parts[0] in EXCLUDE_DIRS:
            continue
        if "__pycache__" in path.parts:
            continue
        copy_file(path, dst / rel)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    for rel in ESSENTIAL_FILES:
        src = ROOT / rel
        if src.exists():
            copy_file(src, OUT / rel)

    for rel_dir in ESSENTIAL_DIRS:
        src = ROOT / rel_dir
        if src.exists():
            copy_tree(src, OUT)

    for pattern in ESSENTIAL_SCRIPT_PATTERNS:
        for src in ROOT.glob(pattern):
            if src.is_file() and src.suffix in {".sh", ".py"}:
                copy_file(src, OUT / src.relative_to(ROOT))

    manifest = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            manifest.append(str(path.relative_to(OUT)))

    (OUT / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"Wrote submission bundle to {OUT}")
    print(f"Included {len(manifest)} files")


if __name__ == "__main__":
    main()
