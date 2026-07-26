# DOCX QA record

This record distinguishes a locally validated artifact from an authorized
Google Drive/Google Docs distribution.

## Current generic handoff

| Field | Result |
|---|---|
| Source | `docs/index.html` |
| Output | `deliverables/search-routing-quality-handoff.docx` |
| Build date | 2026-07-26 |
| Build SHA-256 | `7206f2fd5b414a1b09e514294059e733e13b465b741f8f3b36a25da26875815a` |
| Python | CPython 3.12.9 |
| Builder | `scripts/build_handoff_docx.py` |
| Figure renderer | `rsvg-convert`, fixed light palette, 2040 px wide |
| Structural/privacy check | PASS |
| Reproducibility check | PASS — two clean builds had identical SHA-256 |
| Office open/render check | PASS — LibreOffice 26.2.5.2 |
| Rendered pages | 22 |
| Visual review | PASS — every page inspected on 2026-07-26 |
| Reviewer | Codex |
| Google Docs import/access test | NOT RUN — no approved Drive destination or upload authority was provided |
| Artifact status | ARTIFACT-READY GENERIC TEMPLATE; NOT TEAM-SHARE-READY PRODUCTION DOCUMENT |

## Structural and privacy findings

- Valid OOXML/OPC ZIP; no corrupt members.
- One native title, 12 native Heading 1 sections, 18 native Heading 2
  subsections, and 21 native list items.
- Four editable data tables with fixed widths, repeatable header rows, and no
  fixed row heights.
- Five inline embedded PNG figures, five captions, and five nonempty alt-text
  descriptions; no floating or externally linked media.
- Explicit US Letter page geometry and margins.
- No macros, comments, tracked changes, hidden text, embedded files, external
  relationships, custom properties, or nonempty creator/last-modifier metadata.
- No custom XML stores or document thumbnail remain.
- No JavaScript, CSS variables, theme controls, inline SVG, or data URIs in the
  DOCX.
- Nine visible `[FILL: ...]` prompts remain by design in this generic fixture.
  A production-specialized build must pass
  `scripts/check_handoff_docx.py --require-complete`.

## Visual findings

All 22 rendered pages were reviewed. Headings, tables, notation boxes, callouts,
figures, legends, captions, highlighted specialization prompts, headers,
footers, and page numbers are legible. No clipping, overflow, broken equations,
caption separation, unreadable chart labels, accidental blank pages, or table
overrun was observed.

## Required Google Docs smoke test

After Phase B and only with separate upload authority, an authorized owner must
import a copy into the approved restricted Drive location and record:

- Drive destination and intended audience;
- exact link-sharing/access setting before and after import;
- tester and date;
- heading outline/navigation;
- all four tables;
- all five figures, legends, alt text, and captions;
- all three equations;
- approved hyperlinks;
- page breaks, headers/footers, and final page; and
- PASS/FAIL plus any accepted reflow differences.

Do not mark the production document team-share-ready until that test passes.
