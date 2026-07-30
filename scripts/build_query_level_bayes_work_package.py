#!/usr/bin/env python3
"""Build and verify the query-level Bayesian-methods handoff ZIP."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work-packages" / "query-level-bayes"
DELIVERABLE = ROOT / "deliverables" / "query-level-bayes-work-package.zip"
CHECKSUM = DELIVERABLE.with_suffix(DELIVERABLE.suffix + ".sha256")
ARCHIVE_ROOT = "query-level-bayes"
MANIFEST_NAME = "MANIFEST.sha256"
FIXED_TIME = (2000, 1, 1, 0, 0, 0)
MAX_FILE_BYTES = 5 * 1024 * 1024

SOURCE_ALLOWLIST = frozenset(
    {
        "ACCEPTANCE_CRITERIA.md",
        "AGENTS.md",
        "AGENT_BRIEF.md",
        "DATA_CONTRACT.md",
        "DECISIONS_REQUIRED.md",
        "INTERFACES.md",
        "METHOD_CONTRACT.md",
        "README.md",
        "REFERENCES.md",
        "TASK_CHECKLIST.md",
        "config/production.template.json",
        "config/synthetic.example.json",
        "fixtures/README.md",
        "fixtures/aggregation-audit.synthetic.json",
        "fixtures/analysis-manifest.synthetic.json",
        "fixtures/prerequisite-audit.pass.json",
        "fixtures/synthetic-known-truth.csv",
        "fixtures/synthetic-query-counts.csv",
        "schemas/eb-bootstrap-sensitivity.schema.json",
        "schemas/prerequisite-audit.schema.json",
        "schemas/query-counts.schema.json",
        "schemas/query-posteriors.schema.json",
        "scripts/check_package.py",
        "starter/interfaces.py",
    }
)

FORBIDDEN_PARTS = {
    ".env",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "credentials",
    "outputs",
    "posterior",
    "production-data",
    "secrets",
}
FORBIDDEN_SUFFIXES = {
    ".arrow",
    ".feather",
    ".key",
    ".nc",
    ".netcdf",
    ".parquet",
    ".pem",
    ".pkl",
    ".pickle",
    ".pyc",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_files() -> list[Path]:
    if not SOURCE.is_dir():
        raise ValueError(f"missing source directory: {SOURCE}")

    files: list[Path] = []
    for path in sorted(SOURCE.rglob("*")):
        relative = path.relative_to(SOURCE)
        if path.is_symlink():
            raise ValueError(f"symlinks are forbidden: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"unsupported source entry: {relative}")
        relative_text = relative.as_posix()
        if relative_text not in SOURCE_ALLOWLIST:
            raise ValueError(
                "unreviewed file is not on the release allowlist: "
                f"{relative_text}"
            )
        if MANIFEST_NAME in relative.parts:
            raise ValueError(f"{MANIFEST_NAME} is generated and must not be checked in")
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            raise ValueError(f"forbidden path in package: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise ValueError(f"forbidden file type in package: {relative}")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"file exceeds {MAX_FILE_BYTES} bytes: {relative}")
        files.append(path)

    if not files:
        raise ValueError("work package contains no files")
    observed = {path.relative_to(SOURCE).as_posix() for path in files}
    missing = sorted(SOURCE_ALLOWLIST - observed)
    if missing:
        raise ValueError(f"release allowlist entries are missing: {missing}")
    return files


def manifest_bytes(files: list[Path]) -> bytes:
    lines = []
    for path in files:
        relative = path.relative_to(SOURCE).as_posix()
        data = path.read_bytes()
        if b"\r\n" in data:
            raise ValueError(f"CRLF line endings are not allowed: {relative}")
        lines.append(f"{sha256_bytes(data)}  {relative}\n")
    return "".join(lines).encode("utf-8")


def zip_info(name: str, *, directory: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.create_system = 3
    mode = 0o755 if directory else 0o644
    file_type = 0o040000 if directory else 0o100000
    info.external_attr = (file_type | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build(destination: Path) -> None:
    files = source_files()
    manifest = manifest_bytes(files)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        archive.writestr(zip_info(f"{ARCHIVE_ROOT}/", directory=True), b"")
        for path in files:
            relative = path.relative_to(SOURCE).as_posix()
            archive.writestr(
                zip_info(f"{ARCHIVE_ROOT}/{relative}"),
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
        archive.writestr(
            zip_info(f"{ARCHIVE_ROOT}/{MANIFEST_NAME}"),
            manifest,
            compress_type=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        )


def checked_archive_members(archive: zipfile.ZipFile) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    for info in archive.infolist():
        name = info.filename
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError(f"unsafe archive path: {name}")
        if not pure.parts or pure.parts[0] != ARCHIVE_ROOT:
            raise ValueError(f"member outside {ARCHIVE_ROOT}/: {name}")
        unix_mode = (info.external_attr >> 16) & 0o170000
        if unix_mode == 0o120000:
            raise ValueError(f"archive contains symlink: {name}")
        if info.is_dir():
            continue
        if name in members:
            raise ValueError(f"duplicate archive member: {name}")
        members[name] = archive.read(info)
    return members


def verify_archive(path: Path, *, run_checker: bool) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"corrupt archive member: {bad_member}")
        members = checked_archive_members(archive)

    manifest_path = f"{ARCHIVE_ROOT}/{MANIFEST_NAME}"
    if manifest_path not in members:
        raise ValueError(f"archive is missing {manifest_path}")

    manifest_data = members.pop(manifest_path)
    declared: dict[str, str] = {}
    for line in manifest_data.decode("utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or len(digest) != 64:
            raise ValueError(f"invalid manifest line: {line!r}")
        member_name = f"{ARCHIVE_ROOT}/{relative}"
        if member_name in declared:
            raise ValueError(f"duplicate manifest entry: {relative}")
        declared[member_name] = digest

    if set(declared) != set(members):
        missing = sorted(set(declared) - set(members))
        extra = sorted(set(members) - set(declared))
        raise ValueError(f"manifest/member mismatch; missing={missing}, extra={extra}")
    for name, expected in declared.items():
        observed = sha256_bytes(members[name])
        if observed != expected:
            raise ValueError(f"hash mismatch for {name}")

    if run_checker:
        with tempfile.TemporaryDirectory(prefix="query-level-bayes-verify-") as tmp:
            extraction_root = Path(tmp)
            for name, data in members.items():
                destination = extraction_root / PurePosixPath(name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            package = extraction_root / ARCHIVE_ROOT
            (package / MANIFEST_NAME).write_bytes(manifest_data)
            subprocess.run(
                [sys.executable, "scripts/check_package.py"],
                cwd=package,
                check=True,
            )


def expected_checksum(path: Path) -> str:
    return f"{sha256_bytes(path.read_bytes())}  {path.name}\n"


def check_committed_artifact() -> None:
    if not DELIVERABLE.is_file() or not CHECKSUM.is_file():
        raise ValueError("committed ZIP and checksum are both required")

    with tempfile.TemporaryDirectory(prefix="query-level-bayes-build-") as tmp:
        candidate = Path(tmp) / DELIVERABLE.name
        build(candidate)
        if candidate.read_bytes() != DELIVERABLE.read_bytes():
            raise ValueError(
                "committed ZIP is stale; run "
                "python scripts/build_query_level_bayes_work_package.py"
            )

    recorded = CHECKSUM.read_text(encoding="utf-8")
    expected = expected_checksum(DELIVERABLE)
    if recorded != expected:
        raise ValueError("committed ZIP checksum is stale or malformed")
    verify_archive(DELIVERABLE, run_checker=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the committed ZIP is current, safe, and self-contained",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.check:
            check_committed_artifact()
            print(f"PASS: {DELIVERABLE.relative_to(ROOT)} is current and verified")
            return 0

        build(DELIVERABLE)
        verify_archive(DELIVERABLE, run_checker=True)
        CHECKSUM.write_text(expected_checksum(DELIVERABLE), encoding="utf-8")
        print(f"built {DELIVERABLE.relative_to(ROOT)}")
        print(f"wrote {CHECKSUM.relative_to(ROOT)}")
        return 0
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
