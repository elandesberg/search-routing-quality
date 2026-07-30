# Work-agent brief

## Objective

Implement and compare:

1. empirical-Bayes beta-binomial regression; and
2. full hierarchical Bayes;

for query-level randomized AIO treatment effects and credible/posterior
intervals. Both methods must accept the same validated counts, support
query-length prediction, and produce comparable probability-scale summaries.

The implementation should support decision analysis for a static allowlist
proposal, but it must not invent a default business decision rule or apply one
to production.

## Scope

Implement inside this work package. Do not modify the parent repository’s
existing estimator, I/O, simulations, document, or production workflow.

The first release is limited to:

- one binary mature outcome;
- query-level aggregate counts derived from a valid randomized cohort;
- one continuous group-level predictor, query length;
- optional prespecified strata handled as separately labeled fits, not silently
  pooled;
- current shadow-trigger queries with both randomized arms represented; and
- synthetic validation.

Continuous, count, censored, delayed, repeated-outcome, or treatment-on-treated
extensions are out of scope until separately specified.

## Required workflow

### Phase 0 — prerequisite gate

Implement the prerequisite audit before model code can run. It must fail closed
when randomization, the control shadow trigger, policy versions, earliest
shadow-trigger-positive uniqueness, outcome maturity, binary-outcome
suitability, or required strata handling is not approved.

### Phase 1 — data and feature contracts

- Validate event-to-count aggregation and aggregate inputs.
- Use opaque canonical query IDs and record canonicalization version.
- Define query length from pre-treatment canonical query representation.
- Fit standardization on the analysis data and record its parameters.
- Reject missing, nonfinite, post-treatment, or outcome-selected features.

### Phase 2 — empirical Bayes

- Estimate beta-binomial regression hyperparameters by marginal maximum
  likelihood using all queries and both arms.
- Support a query-length baseline term and treatment-by-length interaction.
- Produce conjugate arm-level conditional posteriors and paired effect draws.
- Add a hyperparameter/bootstrap sensitivity so the omitted EB uncertainty is
  inspectable.
- Never describe plug-in EB intervals as fully Bayesian intervals.

### Phase 3 — full Bayes

- Implement the arm-centered correlated hierarchical logistic model in
  `METHOD_CONTRACT.md`.
- Return posterior draws/InferenceData, not only a CSV summary.
- Implement prior and posterior predictive checks.
- Enforce sampler gates and inspect decision-driving local effects.
- Run the prespecified robust-effect and query-length-basis sensitivities.

### Phase 4 — comparison and policy support

- Produce the shared output schema for both estimators.
- Report interval width, sign/probability disagreement, and expected-value
  disagreement.
- Reconcile traffic-weighted modeled lift with the design-based aggregate A/B.
- Implement a separate optional policy-scoring stage that refuses to run until
  the human decision configuration is complete.
- Keep uncertain removals in probation/holdback proposals.

### Phase 5 — validation and handoff

- Make every fast contract test pass.
- Run known-truth simulations across traffic and query-length ranges.
- Record EB and full-Bayes interval calibration and predictive behavior.
- Run the full-Bayes release profile without weakened diagnostics.
- Produce a validation record, unresolved items, and secure-run instructions.

## Required deliverables

- implementation source and dependency lock;
- exact input validators and prerequisite gate;
- EB and full-Bayes estimators;
- shared posterior-summary and comparison outputs;
- optional explicitly configured static-policy scorer;
- synthetic fixture generator and known-truth simulations;
- automated tests;
- model/predictive/interval-calibration report;
- a concise limitations and secure-production-run guide.

## Definition of done

Done means the synthetic and package acceptance criteria pass, the two methods
use the same estimand/data, EB interval labeling is honest, full-Bayes diagnostics
pass, query-length behavior is tested, decision logic has no implicit defaults,
and no production invocation or routing change has occurred.
