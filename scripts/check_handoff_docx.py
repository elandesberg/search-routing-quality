#!/usr/bin/env python3
"""Structural, portability, and privacy checks for the handoff DOCX."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
DC = "http://purl.org/dc/elements/1.1/"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS = {"w": W, "r": R, "wp": WP, "pr": PR, "dc": DC, "cp": CP}

EXPECTED_HEADINGS = [
    "Five claims",
    "A feature is only as good as its relevant alternative",
    "A definition of quality",
    "Why our current comparison cannot support that definition",
    "Two axes, and how they interact",
    "Why exploration cannot wait",
    "The proposal: buy the information",
    "A dry run in a toy world",
    "The batch version: learning the allowlist from the A/B we already run",
    "Open design questions",
    "Risks, and why they are bounded",
    "What this changes",
]
EXPECTED_TABLE_ROWS = [4, 5, 5, 6]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the Google-Docs handoff DOCX."
    )
    parser.add_argument(
        "docx",
        nargs="?",
        default="deliverables/search-routing-quality-handoff.docx",
        type=Path,
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail if any [FILL: ...] specialization marker remains.",
    )
    parser.add_argument(
        "--expect-generic",
        action="store_true",
        help="Require all nine generic [FILL: ...] markers.",
    )
    return parser.parse_args()


def text_of(node: etree._Element) -> str:
    return "".join(node.xpath(".//w:t/text()", namespaces=NS)).strip()


def main() -> int:
    args = parse_args()
    if args.require_complete and args.expect_generic:
        print(
            "FAIL: --require-complete and --expect-generic are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    path = args.docx.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    try:
        archive = zipfile.ZipFile(path)
        bad_member = archive.testzip()
        if bad_member:
            errors.append(f"corrupt ZIP member: {bad_member}")
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    names = set(archive.namelist())
    required = {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
        "docProps/core.xml",
    }
    missing = sorted(required - names)
    if missing:
        errors.append(f"missing OPC members: {', '.join(missing)}")

    forbidden_names = [
        name
        for name in names
        if name.endswith((".bin", ".vbaProject"))
        or name.startswith("word/comments")
        or name.startswith("word/embeddings/")
        or name.startswith("customXml/")
        or name == "docProps/custom.xml"
        or name == "docProps/thumbnail.jpeg"
    ]
    if forbidden_names:
        errors.append(f"forbidden package members: {', '.join(sorted(forbidden_names))}")

    if "word/document.xml" not in names:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    document = etree.fromstring(archive.read("word/document.xml"))
    relationships = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
    core = etree.fromstring(archive.read("docProps/core.xml"))

    visible_text = "\n".join(document.xpath(".//w:t/text()", namespaces=NS))
    forbidden_text = ("<script", "var(--", "data:image", "class=\"", ">Dark<")
    for token in forbidden_text:
        if token in visible_text:
            errors.append(f"forbidden source artifact in visible text: {token}")

    for tag in ("ins", "del", "moveFrom", "moveTo", "vanish", "webHidden"):
        if document.xpath(f".//w:{tag}", namespaces=NS):
            errors.append(f"tracked or hidden content present: w:{tag}")

    external = relationships.xpath(
        './/pr:Relationship[@TargetMode="External"]', namespaces=NS
    )
    forbidden_external = [
        relationship
        for relationship in external
        if not relationship.get("Type", "").endswith("/hyperlink")
    ]
    if forbidden_external:
        errors.append("non-hyperlink external document relationships are present")

    anchors = document.xpath(".//wp:anchor", namespaces=NS)
    inlines = document.xpath(".//wp:inline", namespaces=NS)
    if anchors:
        errors.append(f"found {len(anchors)} floating images; expected none")
    if len(inlines) != 5:
        errors.append(f"found {len(inlines)} inline images; expected 5")

    descriptions = [
        (node.get("descr") or "").strip()
        for node in document.xpath(".//wp:inline/wp:docPr", namespaces=NS)
    ]
    if len([value for value in descriptions if value]) != 5:
        errors.append("each of the five figures must have nonempty alt text")

    media = sorted(name for name in names if name.startswith("word/media/"))
    if len(media) != 5:
        errors.append(f"found {len(media)} embedded media files; expected 5")
    non_png = [name for name in media if not name.lower().endswith(".png")]
    if non_png:
        errors.append(f"non-PNG embedded media: {', '.join(non_png)}")

    paragraphs = document.xpath(".//w:body/w:p", namespaces=NS)
    styles: list[tuple[str, str]] = []
    for paragraph in paragraphs:
        style = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
        styles.append((style[0] if style else "", text_of(paragraph)))

    titles = [text for style, text in styles if style == "Title"]
    if titles != ["Compared to what?"]:
        errors.append(f"unexpected title paragraphs: {titles!r}")
    headings = [text for style, text in styles if style == "Heading1"]
    if headings != EXPECTED_HEADINGS:
        errors.append(
            "Heading 1 sequence differs from the controlled source: "
            + " | ".join(headings)
        )
    heading2_count = sum(style == "Heading2" for style, _ in styles)
    if args.expect_generic and heading2_count != 18:
        errors.append(f"found {heading2_count} Heading 2 paragraphs; expected 18")
    elif not args.expect_generic and heading2_count < 18:
        errors.append(
            f"found {heading2_count} Heading 2 paragraphs; expected at least 18"
        )

    list_count = len(
        document.xpath(
            ".//w:body/w:p[w:pPr/w:pStyle[@w:val='ListNumber' or @w:val='ListBullet']]",
            namespaces=NS,
        )
    )
    if args.expect_generic and list_count != 21:
        errors.append(f"found {list_count} real list items; expected 21")
    elif not args.expect_generic and list_count < 21:
        errors.append(f"found {list_count} real list items; expected at least 21")

    tables = document.xpath(".//w:body/w:tbl", namespaces=NS)
    data_tables = [
        table
        for table in tables
        if len(table.xpath("./w:tblGrid/w:gridCol", namespaces=NS)) > 1
    ]
    row_counts = [
        len(table.xpath("./w:tr", namespaces=NS)) for table in data_tables
    ]
    if args.expect_generic and row_counts != EXPECTED_TABLE_ROWS:
        errors.append(f"data-table row counts are {row_counts}; expected {EXPECTED_TABLE_ROWS}")
    elif not args.expect_generic and (
        len(row_counts) != len(EXPECTED_TABLE_ROWS)
        or any(
            actual < minimum
            for actual, minimum in zip(row_counts, EXPECTED_TABLE_ROWS)
        )
    ):
        errors.append(
            "data-table row counts are "
            f"{row_counts}; expected four tables with at least "
            f"{EXPECTED_TABLE_ROWS} rows"
        )
    for index, table in enumerate(data_tables, start=1):
        grid = table.xpath("./w:tblGrid/w:gridCol/@w:w", namespaces=NS)
        if not grid or sum(int(value) for value in grid) != 9360:
            errors.append(f"table {index} does not have a fixed 9360-DXA grid")
        if not table.xpath("./w:tr[1]/w:trPr/w:tblHeader", namespaces=NS):
            errors.append(f"table {index} header row is not marked to repeat")
        if table.xpath(".//w:trHeight", namespaces=NS):
            errors.append(f"table {index} contains fixed row heights")

    captions = [text for style, text in styles if style == "Caption"]
    if len(captions) != 5:
        errors.append(f"found {len(captions)} captions; expected 5")
    if args.expect_generic:
        expected_caption_starts = [
            "Schematic — illustrative shape, not measured data.",
            "Simulation.",
            "Simulation.",
            "Simulation.",
            "Simulation, medians over 40 replications.",
        ]
        for index, expected in enumerate(expected_caption_starts):
            if index >= len(captions) or not captions[index].startswith(expected):
                errors.append(f"caption {index + 1} does not start with {expected!r}")
    else:
        allowed_label = re.compile(
            r"^(Schematic|Synthetic|Simulation|Calibrated simulation|Production)"
            r"(?:[,. —]|$)",
            re.IGNORECASE,
        )
        for index, caption in enumerate(captions, start=1):
            if not allowed_label.match(caption):
                errors.append(
                    f"caption {index} lacks a visible evidence-type label"
                )

    fill_count = len(re.findall(r"\[FILL:", visible_text))
    if args.expect_generic and fill_count != 9:
        errors.append(f"found {fill_count} explicit [FILL:] markers; expected 9")
    elif args.require_complete and fill_count:
        errors.append(
            f"{fill_count} specialization markers remain (--require-complete)"
        )
    elif fill_count and not args.expect_generic:
        warnings.append(
            f"{fill_count} [FILL:] marker(s) remain; "
            "Phase B must resolve them before team distribution"
        )

    section_properties = document.xpath(".//w:sectPr", namespaces=NS)
    if not section_properties:
        errors.append("no explicit page geometry")
    for sect in section_properties:
        page_size = sect.xpath("./w:pgSz", namespaces=NS)
        margins = sect.xpath("./w:pgMar", namespaces=NS)
        if not page_size or page_size[0].get(f"{{{W}}}w") != "12240":
            errors.append("page width is not US Letter")
        if not page_size or page_size[0].get(f"{{{W}}}h") != "15840":
            errors.append("page height is not US Letter")
        if not margins:
            errors.append("page margins are not explicit")

    creator = core.xpath("string(dc:creator)", namespaces=NS).strip()
    last_modified = core.xpath("string(cp:lastModifiedBy)", namespaces=NS).strip()
    if creator or last_modified:
        errors.append("creator/lastModifiedBy metadata was not scrubbed")

    archive.close()
    for warning in warnings:
        print(f"WARN: {warning}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PASS: valid DOCX; native headings/lists/tables; five embedded PNG figures "
        "with alt text; no external, hidden, tracked, macro, or custom-property content"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
