# Query-level Bayes implementation work package

This directory is a self-contained handoff for implementing two estimators of
query-level AIO treatment effects:

1. a transparent empirical-Bayes (EB) beta-binomial regression inspired by the
   baseball example; and
2. a full hierarchical Bayesian model that propagates uncertainty in pooling,
   predictors, and query-level effects.

This is a work package, not an installable Python distribution. The
implementation agent may choose a sensible internal code layout, but must obey
the contracts, outputs, and acceptance gates here.

## The question this package answers

For query \(q\), among randomized opportunities that a versioned, pre-treatment
shadow policy says would trigger AIO under treatment:

\[
\Delta_q =
P(Y=1\mid Z=1,S=1,Q=q)
-
P(Y=1\mid Z=0,S=1,Q=q)
\]

\[
\tau_q = \Delta_q-c_q
\]

where:

- \(Z\) is randomized assignment;
- \(S\) is the assignment-invariant shadow “would trigger AIO” flag;
- \(Y\) is one prespecified binary user/session outcome; and
- \(c_q\) is optional serving cost in outcome-equivalent units.

Both gross lift \(\Delta_q\) and net lift \(\tau_q\) must be reported.

The primary population is **not** “rows where AIO was actually delivered in
treatment.” Actual delivery, fallback, and runtime success occur after
assignment. Conditioning on them would generally break the randomized
comparison. If the shadow trigger cannot be evaluated with the same version and
logic in both arms, the query-level causal analysis is blocked.

## Start here

The implementation agent reads these files in order:

1. [`AGENTS.md`](AGENTS.md) — non-negotiable safety and identification rules.
2. [`AGENT_BRIEF.md`](AGENT_BRIEF.md) — assignment and definition of done.
3. [`METHOD_CONTRACT.md`](METHOD_CONTRACT.md) — estimands and both model
   specifications.
4. [`DATA_CONTRACT.md`](DATA_CONTRACT.md) — event and model-input requirements.
5. [`INTERFACES.md`](INTERFACES.md) — required commands, functions, and outputs.
6. [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md) — tests and release gates.
7. [`DECISIONS_REQUIRED.md`](DECISIONS_REQUIRED.md) — human inputs that cannot
   be guessed.
8. [`REFERENCES.md`](REFERENCES.md) — source material and transfer notes.

Run the package-integrity check immediately:

```bash
python3 scripts/check_package.py
```

The scaffold checker uses only the standard library and supports CPython
3.12+. The implementation agent must add an in-package dependency lock before
introducing numerical libraries; the ZIP does not depend on the parent
repository's environment.

The included fixture is synthetic, uses opaque query IDs, and exists only to
exercise contracts:

```text
fixtures/synthetic-query-counts.csv
fixtures/synthetic-known-truth.csv
fixtures/analysis-manifest.synthetic.json
fixtures/aggregation-audit.synthetic.json
fixtures/prerequisite-audit.pass.json
```

## Required end state

The implementation must produce, from one validated analysis dataset:

- comparable EB and full-Bayes query posterior tables;
- 50%, 80%, and 95% intervals;
- \(P(\Delta_q>0)\) and \(P(\tau_q>0)\);
- query-length prior/effect diagnostics;
- shrinkage and support diagnostics;
- aggregate design-based versus modeled checks;
- EB-versus-full-Bayes disagreement reports; and
- optional static-policy proposals only when an approved decision configuration
  supplies loss, value, capacity, and uncertainty constraints.

No default probability cutoff may silently become an allowlist action.

## What “static allowlist” means here

The output is a frozen proposal for the next operating cycle, not a permanent
truth. A defensible proposal should maximize expected traffic-weighted net value
subject to approved capacity and posterior-risk constraints. Uncertain removals
belong in a probation/holdback tier so the next cycle can test them.

Randomization identifies effects only within the shadow-trigger population and
the experiment’s support. Query length can improve partial pooling; it cannot
identify never-randomized, off-trigger effects.

## Relationship to the parent repository

The existing full-Bayes estimator is useful reference material, but this work
package must be implemented in isolation and must not change or import the
parent repository’s production estimator:

- [`allowlist_model_pymc.py`](https://github.com/elandesberg/search-routing-quality/blob/main/allowlist_model_pymc.py)
- [`production_io.py`](https://github.com/elandesberg/search-routing-quality/blob/main/production_io.py)
- [`production-replication-packet.md`](https://github.com/elandesberg/search-routing-quality/blob/main/production-replication-packet.md)

The implementation agent may port reviewed ideas, not create live cross-package
imports. This keeps the new EB/full-Bayes comparison independently testable and
prevents a handoff experiment from changing an existing production path.
