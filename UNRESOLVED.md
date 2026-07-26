# Unresolved items and human gate

This is the durable blocker log for the handoff. Do not hide an unavailable fact
by deleting its row or by moving it only into a chat response.

## Status definitions

- `OPEN`: unresolved and still blocks the stated phase.
- `ACCEPTED`: a named human accepted the limitation or risk.
- `RESOLVED`: evidence or a decision closed the item.
- `NOT APPLICABLE`: a named human confirmed the item does not apply.

`P0` blocks Phase A or Phase B as stated. `P1` requires a named owner and explicit
human disposition before the pull request is ready for review. `P2` may remain
open if it is transparently documented.

## Current items

| ID | Priority | Blocks | Status | Issue | Required resolution | Owner | Evidence/decision |
|---|---|---|---|---|---|---|---|
| U-001 | P0 | Phase A | OPEN | Production inputs are not yet populated | Complete the required fields in `PRODUCTION_INPUTS.md` or mark each unavailable with an owner | Unassigned | None |
| U-002 | P0 | Phase B | OPEN | Phase A evidence has not been reviewed | Produce the Phase A artifacts and record the human-gate decision before source specialization or production DOCX packaging | Unassigned | None |
| U-003 | P1 | Publication | OPEN | Approved Drive destination, audience, link-sharing setting, upload owner, and deployed access policy are unverified | Record the destination, audience, exact sharing setting, access test, owner, approver, and date | Unassigned | None |
| U-004 | P1 | Phase B | OPEN | Final repository URL for the simulation/replication link is unknown | Record the stable private/internal URL and verify it in the DOCX and optional HTML | Unassigned | None |
| U-005 | P0 | Stage 2b fit | OPEN | The PyMC prior-predictive behavior and prespecified Student-t sensitivity contract are not approved for the production outcome | Complete the model-sensitivity section of `PRODUCTION_INPUTS.md`, review prior-predictive draws, and name the decision-stability criterion | Unassigned | None |
| U-006 | P1 | Team sharing | OPEN | The generic DOCX passed local structural and 22-page render review, but no authorized Google Docs import/access smoke test has been run | After Phase B, import a copy into the approved restricted Drive folder; verify headings, tables, figures/captions, equations, links, final page, and sharing; record owner/date/result in `analysis/docx-qa.md` | Unassigned | Local generic QA recorded in `analysis/docx-qa.md` |

Add new rows for unavailable production facts, evidence contradictions, model or
metric mismatches, privacy concerns, diagnostic failures, and decisions that a
work agent is not authorized to make.

## Human gate record

| Field | Value |
|---|---|
| Gate status | NOT REVIEWED |
| Pull request | NOT CREATED |
| Evidence snapshot/commit | NOT PROVIDED |
| Product approver and date | NOT PROVIDED |
| Analytics approver and date | NOT PROVIDED |
| Privacy/security approver and date | NOT PROVIDED |
| Publication approver and date | NOT PROVIDED |
| Required outputs: DOCX required / HTML yes-no | NOT PROVIDED |
| Approved DOCX filename | NOT PROVIDED |
| Approved Drive destination and audience | NOT PROVIDED |
| Approved link-sharing policy | NOT PROVIDED |
| Upload owner | NOT PROVIDED |
| DOCX privacy reviewer and date | NOT PROVIDED |
| Google Docs import tester, date, and result | NOT PROVIDED |
| Approved outcome \(Y\) | NOT PROVIDED |
| Approved baseline/population/window | NOT PROVIDED |
| Approved cost/latency treatment | NOT PROVIDED |
| Approved proposal parameters | NOT PROVIDED |
| Open questions intentionally retained | NOT PROVIDED |
| Claims changed because of contradictory evidence | NONE RECORDED |
| Conditions on Phase B | NOT PROVIDED |

Valid gate statuses are:

- `NOT REVIEWED`
- `CHANGES REQUESTED`
- `APPROVED FOR PHASE B`

Only `APPROVED FOR PHASE B`, with named approvers and no open Phase B `P0`,
authorizes specialization of `docs/index.html` and local production-DOCX
packaging. It does not authorize Drive upload, sharing changes, or web
publication.
