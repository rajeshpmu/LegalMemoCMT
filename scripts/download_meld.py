from __future__ import annotations

import argparse
import os
import shutil
import ssl
import tarfile
import urllib.request
from urllib.error import URLError
from pathlib import Path


MELD_RAW_URL = "http://web.eecs.umich.edu/~mihalcea/downloads/MELD.Raw.tar.gz"
MELD_CSV_URLS = {
    "train": "https://raw.githubusercontent.com/declare-lab/MELD/master/data/MELD/train_sent_emo.csv",
    "dev": "https://raw.githubusercontent.com/declare-lab/MELD/master/data/MELD/dev_sent_emo.csv",
    "test": "https://raw.githubusercontent.com/declare-lab/MELD/master/data/MELD/test_sent_emo.csv",
}


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} -> {dest}")
    request = urllib.request.Request(url)

    def open_with_context(context: ssl.SSLContext):
        with urllib.request.urlopen(request, context=context) as response, dest.open("wb") as out_file:
            shutil.copyfileobj(response, out_file)

    try:
        import certifi

        secure_context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        # Fall back to the interpreter default trust store if certifi is unavailable.
        secure_context = ssl.create_default_context()

    try:
        open_with_context(secure_context)
    except URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            print("Certificate verification failed; retrying with SSL verification disabled for this host.")
            open_with_context(ssl._create_unverified_context())
        else:
            raise


def extract_tar(path: Path, target_dir: Path) -> None:
    print(f"Extracting {path} -> {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "r:gz") as tar:
        tar.extractall(target_dir)


def extract_recursive(root: Path) -> None:
    for tar_path in list(root.rglob("*.tar.gz")):
        if tar_path.name.endswith(".tar.gz"):
            out_dir = tar_path.parent / tar_path.name.replace(".tar.gz", "")
            if not out_dir.exists():
                extract_tar(tar_path, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download MELD data")
    parser.add_argument("--output", type=str, default="data/MELD", help="Dataset output directory")
    parser.add_argument("--raw", action="store_true", help="Download raw video archive")
    parser.add_argument("--annotations", action="store_true", help="Download annotation CSVs")
    parser.add_argument("--extract", action="store_true", help="Extract archives after download")
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    if not args.raw and not args.annotations:
        args.raw = True
        args.annotations = True

    if args.raw:
        raw_path = out / "MELD.Raw.tar.gz"
        download(MELD_RAW_URL, raw_path)
        if args.extract:
            extract_tar(raw_path, out / "raw")

    if args.annotations:
        ann_dir = out / "annotations"
        for split, url in MELD_CSV_URLS.items():
            download(url, ann_dir / f"{split}_sent_emo.csv")

    if args.extract:
        extract_recursive(out)

    print("MELD download step completed.")
    print("If you downloaded the raw archive, check data/MELD/raw or the extracted folder structure.")


if __name__ == "__main__":
    main()
