# Decisions required

Production analysis is **blocked** until every required estimation decision
below is recorded as `APPROVED` by its named owner. Use `NOT AVAILABLE` plus an
owner and consequence when evidence does not exist; never guess. The optional
policy decisions are required only to score actions. Their absence must leave
all action fields `not_scored`.

Allowed statuses are `NOT PROVIDED`, `PROPOSED`, `APPROVED`, and
`NOT AVAILABLE`.

| ID | Human decision and required record | Blocks | Owner | Status |
|---|---|---|---|---|
| D-01 | Randomization unit (`user` or `query opportunity`), assignment field, propensity source, experiment ID, and SRM rule | All production fitting | NOT PROVIDED | NOT PROVIDED |
| D-02 | For repeated users, independent contribution or approved user-cluster strategy; aggregate counts alone do not solve dependence | All production fitting | NOT PROVIDED | NOT PROVIDED |
| D-03 | Shadow `would_trigger_aio` definition, code/version, evaluation time, and proof that identical logic exists in both arms | Cohort and causal estimand | NOT PROVIDED | NOT PROVIDED |
| D-04 | Canonical query ID/version; for user randomization, first-shadow-trigger-positive ordering, tie-break, and proof that it precedes experimental exposure | Cohort and query effects | NOT PROVIDED | NOT PROVIDED |
| D-05 | Binary outcome, polarity, event source, attribution window, maturity rule, deduplication, and one-outcome-per-unit rule | Likelihood and estimand | NOT PROVIDED | NOT PROVIDED |
| D-06 | Analysis dates, exclusions, required arm support, policy versions, and prespecified retailer/time/version strata | Population and pooling | NOT PROVIDED | NOT PROVIDED |
| D-07 | Versioned tokenizer, token-count representation, missingness rule, standardization population, and linear/spline basis specification | Query-length model | NOT PROVIDED | NOT PROVIDED |
| D-08 | Full-Bayes prior locations/scales and LKJ shape; prior-predictive acceptance; approval of fixed \(\nu=4\) robust sensitivity | Full-Bayes fitting | NOT PROVIDED | NOT PROVIDED |
| D-09 | EB bootstrap unit/method, simulation scenarios, calibration tolerances, predictive tolerances, aggregate-reconciliation tolerance, and what constitutes material EB/HB disagreement | Release decision | NOT PROVIDED | NOT PROVIDED |
| D-10 | Traffic-weight target population and construction, including whether weights represent experiment traffic or the next operating cycle | Aggregate value | NOT PROVIDED | NOT PROVIDED |
| D-11 | Approved secure analysis environment, restricted-output location, retention, privacy review, and permitted aggregate fields | Production read/write | NOT PROVIDED | NOT PROVIDED |
| D-12 | Analytics and product approvers, model-change owner, and disposition path for a failed diagnostic or sensitivity | Release decision | NOT PROVIDED | NOT PROVIDED |

## Optional cost and policy decisions

These fields have no defaults. If cost-adjusted inference is requested, P-01 is
required. If any `keep`, `remove`, `add`, rank, or capacity allocation is
requested, every row P-01 through P-07 is required and must be jointly
versioned as one decision configuration.

| ID | Required decision | Owner | Status |
|---|---|---|---|
| P-01 | Query cost \(c_q\), source, units converting cost to outcome-equivalent probability points, uncertainty treatment, and effective date | NOT PROVIDED | NOT PROVIDED |
| P-02 | Traffic/value weights for the next cycle and treatment of missing or new queries | NOT PROVIDED | NOT PROVIDED |
| P-03 | Explicit action set and asymmetric loss or utility for false inclusion, false removal, and deferral | NOT PROVIDED | NOT PROVIDED |
| P-04 | Capacity, cost, and latency constraints, including whether simultaneous routing creates interference | NOT PROVIDED | NOT PROVIDED |
| P-05 | Posterior-risk constraints and family/portfolio-level risk treatment | NOT PROVIDED | NOT PROVIDED |
| P-06 | Probation, randomized holdback, exploration share, reevaluation cadence, and rollback conditions | NOT PROVIDED | NOT PROVIDED |
| P-07 | Decision owner, approval date, configuration version, next-cycle validity window, and secure destination for restricted proposals | NOT PROVIDED | NOT PROVIDED |

No implementation may infer a probability cutoff from examples, use
\(P(\tau_q>0)>0.5\) or \(>0.8\) as a hidden default, or convert a posterior
summary into an action when this table is incomplete. Production approval
authorizes analysis or scoring only; it does not authorize a routing change.

## Gate record

Before a production run, copy the approved values into a machine-readable,
versioned configuration and record:

- approver name or stable ID, approval date, and evidence URI for each decision;
- configuration hash and code revision;
- whether the authorization covers estimation only or estimation plus policy
  scoring; and
- all `NOT AVAILABLE` items and the resulting limitation.

The prerequisite command must validate this record before reading outcomes.
Changes after outcomes are inspected create a new configuration and require a
fresh run and sensitivity disclosure.
