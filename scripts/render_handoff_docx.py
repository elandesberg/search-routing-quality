#!/usr/bin/env python3
"""Render the handoff DOCX to PDF and page PNGs for visual review."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a handoff DOCX with LibreOffice and Poppler."
    )
    parser.add_argument(
        "docx",
        nargs="?",
        default="deliverables/search-routing-quality-handoff.docx",
        type=Path,
    )
    parser.add_argument(
        "--output-dir",
        default="build/docx-render",
        type=Path,
    )
    parser.add_argument("--dpi", default=160, type=int)
    return parser.parse_args()


def require(command: str, install_hint: str) -> str:
    path = shutil.which(command)
    if not path:
        raise RuntimeError(f"{command} is required. {install_hint}")
    return path


def main() -> int:
    args = parse_args()
    docx = args.docx.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    soffice = require(
        "soffice",
        "Install LibreOffice (macOS: `brew install --cask libreoffice`).",
    )
    pdftoppm = require(
        "pdftoppm",
        "Install Poppler (macOS: `brew install poppler`).",
    )

    with tempfile.TemporaryDirectory(prefix="search-routing-render-") as tmp:
        temp_dir = Path(tmp)
        profile_uri = (temp_dir / "lo-profile").as_uri()
        subprocess.run(
            [
                soffice,
                f"-env:UserInstallation={profile_uri}",
                "--invisible",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp_dir),
                str(docx),
            ],
            check=True,
        )
        converted = temp_dir / f"{docx.stem}.pdf"
        if not converted.exists():
            raise RuntimeError("LibreOffice did not produce the expected PDF.")
        pdf_path = output_dir / f"{docx.stem}.pdf"
        shutil.copy2(converted, pdf_path)

    for old_page in output_dir.glob("page-*.png"):
        old_page.unlink()
    subprocess.run(
        [
            pdftoppm,
            "-png",
            "-r",
            str(args.dpi),
            str(pdf_path),
            str(output_dir / "page"),
        ],
        check=True,
    )
    pages = sorted(output_dir.glob("page-*.png"))
    if not pages:
        raise RuntimeError("Poppler did not produce any page images.")
    print(f"Rendered {len(pages)} pages to {output_dir}")
    print("Inspect every page image before review or upload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
