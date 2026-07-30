# Acceptance criteria

Acceptance is fail-closed and evidence-based. Code existing is not evidence
that a method works. An implementation stage is `PASS`, `BLOCKED`, or
`NOT_RUN`; an unexpected exception is `ERROR`. Only `PASS` may publish a
completed stage artifact.

The numerical sampler gates below are fixed. Application-specific calibration,
predictive, comparison, and policy tolerances must be approved in
`DECISIONS_REQUIRED.md` before outcomes are inspected. The implementation must
not invent a universal tolerance to turn a review into a pass.

## A. Package and isolation

The implementation passes this section only when:

- `python3 scripts/check_package.py` exits zero;
- committed fixtures are synthetic, contain only visibly artificial `q_####`
  IDs, and contain no query text or production identifiers;
- implementation changes stay inside the extracted work package;
- no implementation imports the parent repository estimator or production I/O;
- commands run without installing this directory as a Python distribution;
- the implementation dependency set is locked; and
- the package still runs after extraction when the parent repository is absent.

Any failure is `BLOCKED_PREREQUISITE` or `BLOCKED_DATA_PRIVACY`.

## B. Identification prerequisites

Every production item requires current human approval and inspectable evidence:

1. randomized assignment is valid, immutable, and its unit is known;
2. one versioned shadow `would_trigger_aio` policy was evaluated with identical
   pre-treatment logic in both arms;
3. the shadow computation does not use assignment, actual delivery, fallback,
   outcomes, or later behavior;
4. the primary record is the deterministic earliest shadow-trigger-positive
   query;
5. under user-level randomization, no prior experimental exposure could have
   affected that query;
6. actual AIO delivery did not select the cohort or replace assignment;
7. one prespecified binary outcome and mature attribution window are approved;
8. required strata use `none` or separately labeled fits and are not silently
   pooled; and
9. canonicalization, opaque-ID, tokenizer, length, and privacy provenance are
   approved.

Missing control-arm shadow eligibility blocks treatment-effect estimation.
Analyzing only treatment rows where AIO was delivered is not an alternative.
Tests must induce each failure and verify a stable reason code, exit code `2`,
redacted status, and no model invocation.

## C. Data and feature contracts

Automated tests must cover:

- exact columns and rejection of unexpected fields;
- opaque, domain-separated production IDs and the explicit synthetic-ID
  exception;
- unique primary records and immutable binary assignment;
- non-null, binary, mature outcomes joined once;
- integer counts with `0 <= y <= n`, including `y=0`, `y=n`, and `n=1`;
- positive support in both randomized arms for every modeled query;
- exact event-to-count and aggregate-audit reconciliation;
- version matching for shadow policy, query canonicalization, tokenizer, and
  outcome;
- positive, pre-treatment token counts invariant within query;
- prespecified traffic weights normalized to one; and
- missing-data and exclusion paths that never inspect the outcome to choose
  which rows to keep.

The reference length transform is

\[
z_q =
\frac{\log(1+\mathrm{token\_count}_q)-\bar\ell}{s_\ell},
\]

using one unweighted record per unique retained query. A test must reproduce
the stored mean and sample standard deviation to `1e-12`, demonstrate identical
features in both estimators, and block missing, constant, nonfinite,
post-treatment, or outcome-selected length features. Predictions outside the
observed length range are marked outside support and cannot enter a primary
policy proposal.

Failure is `BLOCKED_DATA_CONTRACT`, `BLOCKED_DATA_PRIVACY`, or the more specific
reason code in `DATA_CONTRACT.md`.

## D. Empirical-Bayes estimator

### Fit and conjugate update

Tests against direct high-precision calculations must establish:

- the beta-binomial marginal log likelihood and fitted predictions are finite;
- multiple prespecified dispersed starts reach the same reviewed optimum
  within the configured numerical tolerance;
- coefficients are finite, concentrations are positive and interior, and
  optimizer/boundary diagnostics are retained;
- the implementation supports `y=0`, `y=n`, and `n=1` cells without clipping;
- conditional posterior Beta parameters equal prior parameters plus observed
  successes and failures;
- posterior means equal the analytic shrinkage formula; and
- sparse cells shrink more toward their length-conditioned population mean
  than otherwise comparable high-volume cells.

An optimizer failure, unreviewed boundary solution, or unidentified
hyperparameter yields `BLOCKED_EB_FIT`.

### Interval semantics and hyperparameter sensitivity

- Every primary EB interval is labeled `plug_in_eb_interval`.
- 50%, 80%, and 95% intervals are nested and remain on the probability/effect
  support.
- Paired arm draws reproduce direct reference effect calculations within
  documented Monte Carlo error.
- A prespecified randomization-unit bootstrap, or a documented parametric
  beta-binomial bootstrap when only valid aggregates exist, refits the entire
  EB model.
- Bootstrap failure rate, interval width, sign probability, length band, and
  traffic band behavior are reported without dropping failed replicates.

Bootstrap and plug-in results remain distinct. Coverage or stability outside
the approved, simulation-calibrated tolerance is
`BLOCKED_EB_DIAGNOSTICS` for decision use; it is not repaired by relabeling a
plug-in interval as a credible interval.

## E. Full hierarchical Bayes

Before a release run, exact proper priors and broad plausible probability-scale
ranges receive prior-predictive approval. Library defaults are not approval.

The release profile uses at least four chains. All of these gates must pass:

- maximum rank-normalized split \(\widehat R\) is strictly less than `1.01`;
- minimum bulk and tail ESS is strictly greater than `400` for every
  hyperparameter, aggregate estimand, and decision-driving query effect;
- post-warmup divergences equal zero;
- energy/BFMI and treedepth diagnostics pass their prespecified
  implementation-specific review;
- no nonfinite log density or sample statistic exists;
- Monte Carlo error is small relative to posterior uncertainty under the
  prespecified reporting rule; and
- no unexplained chain-specific location or scale anomaly remains.

The implementation may increase warmup/draws or use a justified
reparameterization. It may not lower a gate, delete a difficult query after
seeing its posterior, or accept divergences. It must retain checksum-valid
InferenceData/posterior draws; a summary table alone cannot pass.

Required prior and posterior predictive checks cover arm, query length,
traffic, approved stratum, zero/all-success cells, dispersion, and the
aggregate treatment-control contrast. Their statistics and acceptance
tolerances are fixed before outcome review. Failure is
`BLOCKED_PREDICTIVE_CHECK` or `BLOCKED_FULL_BAYES_DIAGNOSTICS`.

## F. Known-truth validation

The synthetic suite spans:

- no, moderate, and strong pooling;
- null, positive, and negative effects;
- linear and nonlinear length relationships;
- null and non-null treatment-by-length interactions;
- balanced and imbalanced arms;
- `n=1`, sparse, medium-, and high-volume queries;
- zero/all-success cells;
- correlated baseline and treatment effects; and
- a heavy-tailed query-effect scenario.

For each estimator, report parameter/effect recovery, bias, RMSE, interval
width, and 50%, 80%, and 95% empirical coverage overall and by prespecified
traffic-by-length bands. Compare query-effect RMSE with raw/unpooled and
complete-pooling baselines.

The simulation count and coverage tolerances must provide enough precision for
the approved application and be recorded before the release suite runs. A
Wilson/binomial interval or simulation standard error must accompany coverage
estimates. Existing approximate negative evidence from another estimator or
fixture is not a passing result for this implementation.

Failure of a prespecified recovery or calibration tolerance is
`BLOCKED_CALIBRATION`; the failing scenario remains visible.

## G. Sensitivity and estimator comparison

The release record includes:

1. primary full Bayes with correlated normal query effects;
2. the fixed-\(\nu=4\) robust treatment-effect sensitivity;
3. the prespecified nonlinear query-length sensitivity; and
4. plug-in versus bootstrap-aware EB summaries.

EB and full Bayes must have exactly the same query keys, counts, length
features, traffic weights, costs, outcome, and versions. The shared table must
match `schemas/query-posteriors.schema.json` and distinguish interval kinds.
No query may silently disappear.

Report, before rounding:

- interval-width and sign-probability differences;
- gross and net posterior-mean differences;
- all prespecified sensitivity deltas;
- high-volume convergence toward raw randomized contrasts; and
- material sign, interval, probability, or expected-value disagreements under
  the approved tolerance.

Model disagreement is not automatically a software defect, but an unreviewed
material disagreement blocks policy scoring with `BLOCKED_COMPARISON`. Neither
method is silently chosen because it produces the more favorable result.

## H. Aggregate randomized check

For the exact same shadow-trigger cohort:

1. compute the prespecified design-based aggregate A/B effect from randomized
   assignment;
2. compute each estimator's traffic-weighted aggregate posterior effect; and
3. compare them using the prespecified uncertainty-compatible tolerance.

Weights and target population are immutable before comparison. A material
incompatibility is `BLOCKED_AGGREGATE_RECONCILIATION`; it triggers model/data
review, not post hoc reweighting.

## I. Privacy and atomic outputs

Tests must demonstrate:

- restricted roots inside any Git worktree are rejected;
- traversal and symlink escapes are rejected;
- directories/files receive approved owner-only permissions;
- logs, statuses, model cards, and exceptions reveal no production IDs, row
  values, query text, sensitive local paths, credentials, or signed URLs;
- staging is not published after validation, fit, diagnostic, checksum, or
  write failure;
- the completed marker and `latest` pointer change only after atomic
  publication; and
- a completed run ID cannot be overwritten.

Failure is `BLOCKED_OUTPUT_SAFETY` or `BLOCKED_DATA_PRIVACY`.

## J. Decision-support boundary

Inference completion does not authorize an allowlist. Policy scoring is
`BLOCKED_DECISION_CONFIG` unless an approved configuration explicitly supplies
cost/value units, traffic, asymmetric loss or utility, capacity,
portfolio/posterior-risk constraints, tie handling, probation/holdback,
exploration, validity period, and owner.

Configured tests verify that:

- gross and net effects remain separate;
- no log-odds coefficient is used as product lift;
- constraints hold exactly under the configured rule;
- uncertain or sensitivity-unstable removals enter probation/holdback;
- outside-support queries cannot enter a proposal;
- no probability cutoff or zero cost appears implicitly; and
- output is a static, expiring next-cycle proposal that no package command can
  publish or apply.

## K. Definition of acceptance

The implementation is ready for a secure production review only when every
applicable synthetic, contract, estimator, diagnostic, calibration,
comparison, failure-path, and output-safety test passes; configurations and
artifacts have immutable fingerprints; limitations are recorded; and no
production data or routing action has occurred.

A production analysis is complete only after current human approvals, valid
restricted data, both estimators, all applicable diagnostics, cross-method and
aggregate review, and atomic restricted publication succeed. Production model
completion still does not authorize a routing change.
