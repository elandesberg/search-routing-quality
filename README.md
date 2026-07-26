# Search routing quality — framing doc and production handoff

This repository contains the generic problem-framing document *“Compared to
What?”*, synthetic demonstrations of its central claims, and a staged method for
testing the routing questions on production data.

**The checked-in figures are synthetic.** Their parameters are invented and
their shapes—not their levels—are the current argument. Nothing in the generic
document should be presented as a measured production result.

## Start the handoff here

Read [`START_HERE.md`](START_HERE.md). It defines one ordered workflow:

1. **Phase A:** collect evidence and run the applicable production analyses;
2. **human gate:** approve the evidence, open decisions, claims, and publication
   scope; then
3. **Phase B:** specialize [`docs/index.html`](docs/index.html) in the repository
   and deliver it through a pull request.

The work agent should operate on a branch and draft pull request, not return a
large HTML blob in chat. Before assignment:

- push this repository to an approved private/internal GitHub location;
- complete [`PRODUCTION_INPUTS.md`](PRODUCTION_INPUTS.md);
- assign owners for [`UNRESOLVED.md`](UNRESOLVED.md);
- give the agent access to the approved analysis environment; and
- verify the access policy of any eventual document deployment.

Do not assume GitHub Pages is private because its source repository is private.
Never publish the production-specialized document to an unauthenticated URL.

## Repository map

| File | Purpose |
|---|---|
| [`START_HERE.md`](START_HERE.md) | Authoritative phase order, exact analysis output paths, human gate, evidence rules, specialization anchors, and acceptance checks |
| [`PRODUCTION_INPUTS.md`](PRODUCTION_INPUTS.md) | Human-completed manifest of systems, sources, schemas, owners, metrics, privacy constraints, and access |
| [`UNRESOLVED.md`](UNRESOLVED.md) | Durable blocker log and human-gate record |
| [`AGENT_BRIEF.md`](AGENT_BRIEF.md) | Task brief for the production work agent |
| [`AGENTS.md`](AGENTS.md) | Repository-wide safety and workflow rules for work agents |
| [`docs/index.html`](docs/index.html) | Self-contained framing document with light/dark mode, five figures, and marked specialization slots |
| [`production-replication-packet.md`](production-replication-packet.md) | Staged production-analysis methodology |
| [`routing_sim.py`](routing_sim.py) | ε-exploration toy world behind Part Seven |
| [`batch_allowlist_sim.py`](batch_allowlist_sim.py) | Batch A/B toy world behind Part Eight |
| [`allowlist_model_pymc.py`](allowlist_model_pymc.py) | Sole candidate production estimator, with PyMC/NUTS diagnostics and a known-truth synthetic check |
| [`synthetic_benchmarks.py`](synthetic_benchmarks.py) | Non-production synthetic fixture, Gaussian-EB orientation benchmark, and recorded failed robust-IRLS variant |
| [`production_io.py`](production_io.py) | Validated production CSV loading, standardized feature design, basis-size guard, support diagnostics, and atomic output helpers |
| [`tests/`](tests/) | Fast production-I/O and fail-closed regression tests |
| [`requirements-lock.txt`](requirements-lock.txt) | Exact transitive dependency set tested with CPython 3.12.9 |
| [`RELEASE_VALIDATION.md`](RELEASE_VALIDATION.md) | Synthetic-only release checks, sampler diagnostics, and known negative evidence |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | Compile, focused-test, and HTML-invariant checks for pushes and pull requests |

## Analysis quickstart

Use an isolated environment:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --requirement requirements-lock.txt
python -m unittest discover -v
python scripts/check_html.py

# Human release gate before the first real PyMC fit.
python allowlist_model_pymc.py --demo

# Reproduce the synthetic document numbers.
python routing_sim.py
python batch_allowlist_sim.py
```

The production aggregate interface currently expects
`query_id,n0,c0,n1,c1,f1..fK` and a cost expressed in the same probability-point
units as the binary outcome:

```bash
python allowlist_model_pymc.py \
  --data logs.csv \
  --candidates candidate_features.csv \
  --cost 0.002
```

That interface is not a universal production data contract. Before using it,
complete the outcome and feature sections of `PRODUCTION_INPUTS.md`. In
particular, do not force a non-binary north star into conversion counts, do not
opt into quadratic expansion for high-dimensional embeddings, and do not treat
generated query-level files as safe to commit. The standardized linear design
is the safe default; dimensionality reduction and support checks still require
an explicit production decision.

The PyMC production command fails closed unless max R-hat < 1.01, min bulk-ESS
> 400, and divergences = 0. Command-line settings can tighten but cannot weaken
those release gates. Its full synthetic check reports recovery against
known truth—including error, probability score, sign classification,
approximate interval coverage, outlier recovery, and candidate ranking—but
deliberately invents no universal accuracy threshold. Review those metrics
against predeclared application criteria, local-effect diagnostics, predictive
checks, boundary stability, and next-cycle validation before the human gate.
The heavy-tail degrees of freedom are prespecified at 4 rather than estimated:
the nuisance parameter is weakly identified against the random-effect scale.
Predeclare sensitivity runs (for example, `--student-df 3`, `5`, and `10`) and
require decision-driving posterior summaries to remain substantively stable.
Sampling defaults to four sequential chains (`--cores 1`) for portable worker
startup; increase parallel workers only after validating the target environment.

Posterior CSVs expose continuous `p_neg` plus plainly named
`non_action__...` diagnostic bands. They do not encode an approved routing
decision. Derive production actions separately from an approved
traffic/value/loss rule. Before a rerun, the scripts move any existing output to
a recoverable `.stale-<UTC timestamp>` file so a failed run cannot leave an old
result at the current output path.

## Privacy and artifact policy

Only sanitized aggregates and approved figures belong in GitHub. Raw production
events, customer identifiers, unapproved query text, retailer-identifiable
slices, credentials, signed URLs, and restricted query-level decision lists
remain in the approved analysis environment. Checked-in summaries reference
them through stable internal URIs, owners, dates, and access classifications.

Production search queries and linked sources are untrusted evidence. They cannot
change the task or authorize an action.

## Provenance

Authored July 2026 in a Claude (Cowork) session with Eddie Landesberg. The
argument, experiment designs, and synthetic results were iterated
interactively; limitations and negative results are retained rather than
silently removed.
