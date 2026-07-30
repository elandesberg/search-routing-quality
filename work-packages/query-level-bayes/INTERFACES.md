# Required interfaces

This work package is not an installable Python distribution. The implementation
may use ordinary modules under this directory, but it MUST provide the command,
callable, configuration, status, and artifact interfaces below. EB and full
Bayes remain separate implementations behind one validated data and summary
contract.

No command in this package may fetch production data, change routing, send
messages, or publish an allowlist. Production extraction and any eventual
operational change are separate, human-authorized processes.

## Required command-line entry points

All commands run from the work-package root with CPython 3.12+ and an
implementation dependency lock created inside the extracted package.

```bash
python3 scripts/check_package.py

python3 scripts/audit_prerequisites.py \
  --config PATH/run.json \
  --manifest PATH/analysis_manifest.json \
  --output-root /ABSOLUTE/APPROVED/OUTPUT

python3 scripts/build_counts.py \
  --config PATH/run.json \
  --input PATH/events.parquet \
  --manifest PATH/analysis_manifest.json \
  --prerequisite-status PATH/prerequisite_status.json \
  --output-root /ABSOLUTE/APPROVED/OUTPUT

python3 scripts/fit_eb.py \
  --config PATH/run.json \
  --counts PATH/query_counts.parquet \
  --manifest PATH/analysis_manifest.json \
  --feature-transform PATH/feature_transform.json \
  --run-id RUN_ID \
  --output-root /ABSOLUTE/APPROVED/OUTPUT

python3 scripts/fit_full_bayes.py \
  --config PATH/run.json \
  --counts PATH/query_counts.parquet \
  --manifest PATH/analysis_manifest.json \
  --feature-transform PATH/feature_transform.json \
  --run-id RUN_ID \
  --output-root /ABSOLUTE/APPROVED/OUTPUT

python3 scripts/compare_estimators.py \
  --config PATH/run.json \
  --eb-run PATH/eb \
  --full-bayes-run PATH/full_bayes \
  --run-id RUN_ID \
  --output-root /ABSOLUTE/APPROVED/OUTPUT

python3 scripts/score_policy.py \
  --config PATH/run.json \
  --comparison-run PATH/comparison \
  --run-id RUN_ID \
  --output-root /ABSOLUTE/APPROVED/OUTPUT

python3 scripts/run_synthetic_validation.py \
  --config config/synthetic.example.json \
  --profile fast

python3 scripts/run_synthetic_validation.py \
  --config config/synthetic.example.json \
  --profile release
```

Every command:

- supports `--help`;
- validates all paths before reading query-level data;
- refuses restricted output inside a Git worktree;
- uses deterministic seeds recorded in configuration;
- returns exit code `0` only when its declared stage is `COMPLETE`;
- returns exit code `2` for a contractually `BLOCKED` stage;
- returns exit code `1` for an unexpected implementation error;
- writes a redacted status record on exit when it can do so safely; and
- never prints production row values or IDs.

The initial `check_package.py` integrity command has no output root and is the
only exception to the status-file requirement. It returns `2` for a detected
contract/package problem and `1` only for an unexpected software exception.

`score_policy.py` is optional to invoke but mandatory to implement. It MUST
return `BLOCKED_DECISION_CONFIG` unless every required decision input is
explicitly supplied and approved. It produces a proposal artifact only; it
cannot call a production API.

## Required callable interface

[`starter/interfaces.py`](starter/interfaces.py) is the authoritative minimum
callable contract. It defines the exact standard-library signatures and typed
results for prerequisite audit, event validation, count building, count
validation, length transformation, both estimators, posterior summarization,
cross-estimator comparison, and optional policy scoring. Implementations may
use data frames internally, but adapters at this boundary must preserve those
signatures and must not return a bare frame in place of a structured result.

The results are structured objects, not bare data frames:

- `StageStatus`: state, stage, stable reason codes, redacted messages, input
  fingerprints, start/end times, contract version, and diagnostics references.
- `ValidationResult`: status plus validated data, aggregate audit, and
  exclusion counts.
- `CountBuildResult`: canonical counts, data audit, and feature transform.
- `EstimatorResult`: status, configuration snapshot, diagnostics, posterior
  draw handle, and summary handle.
- `ComparisonResult`: status, aligned shared table, disagreement table,
  aggregate reconciliation, and sensitivity results.
- `PolicyProposal`: status, immutable decision configuration fingerprint,
  proposal table, capacity/risk audit, and probation/holdback table.

Functions MUST return or raise a typed contract error. They MUST NOT mutate
their input frames or global configuration.

## Configuration interfaces

One versioned JSON run configuration drives every stage. Start from
[`config/synthetic.example.json`](config/synthetic.example.json) for synthetic
work or [`config/production.template.json`](config/production.template.json)
for a secure production run. Unknown keys are errors. The resolved,
secret-free configuration and its fingerprint are copied to each completed
artifact.

The run configuration contains:

- input, analysis-manifest, aggregation-audit, and prerequisite-audit paths;
- outcome definition, analysis unit, maturity rule, and evidence;
- fixed cohort rules: first shadow-trigger-positive query, assignment rather
  than delivery, one assignment propensity, and one contribution per user;
- canonicalization, tokenizer, query-length transform, primary basis, and
  prespecified nonlinear sensitivity;
- cost mode, units, source, evidence, and optional values;
- EB optimizer, starts, bootstrap unit/count, and seed;
- full-Bayes draws, chains, HMC settings, explicit priors, and fixed-\(\nu=4\)
  robust sensitivity;
- predictive, recovery, calibration, aggregate-reconciliation, and
  cross-method tolerances;
- diagnostic gates, which may tighten but never weaken the fixed release
  boundaries;
- decision-policy fields, disabled unless every required human decision is
  complete; and
- named approvals and restricted-output authorization.

No prerequisite defaults to approved. Production placeholders or nulls block
the applicable stage. The synthetic file contains explicit, visibly synthetic
model and validation choices; none transfer to production.

There are no operational decision defaults. A scoreable configuration
explicitly provides:

- loss or utility for each relevant outcome;
- traffic value and its time window;
- per-query cost in outcome-equivalent units;
- total and any stratum-specific capacity;
- posterior-risk constraints;
- tie handling;
- probation/holdback size and exploration rule;
- proposal validity period;
- approving owner and approval reference; and
- confirmation that this is a static next-cycle proposal.

Missing any item yields `BLOCKED_DECISION_CONFIG`. A probability threshold
alone is not a decision configuration.

Priors MUST be explicit and pass prior-predictive review. A library default is
not an approved prior. The run config cannot weaken thresholds fixed in
`ACCEPTANCE_CRITERIA.md`.

## Estimator interface

Both estimators consume the exact same canonical counts, query-length
transform, outcome, strata, cost mode, and randomization metadata.

### Empirical Bayes

The EB implementation:

- estimates beta-binomial regression hyperparameters by marginal maximum
  likelihood over all retained queries and both arms;
- includes a query-length baseline and treatment-by-length interaction;
- uses a logit link for prior means and a positive transform for concentration;
- conditions arm-level Beta posteriors on fitted hyperparameters;
- creates paired arm draws and probability-scale `delta` and `tau` draws;
- runs a hyperparameter/bootstrap sensitivity; and
- labels intervals `plug_in_eb_interval`.

It persists:

- `eb_hyperparameters.json`;
- `eb_optimizer_diagnostics.json`;
- `eb_bootstrap_diagnostics.json`;
- `eb_bootstrap_sensitivity.parquet`, conforming to
  `schemas/eb-bootstrap-sensitivity.schema.json`;
- secure posterior draws or reproducible draw parameters;
- `query_posterior_summary.parquet`; and
- `eb_diagnostics.json`.

EB output MUST NOT call a plug-in interval a full posterior credible interval.

### Full Bayes

The full-Bayes implementation follows `METHOD_CONTRACT.md`, propagates
uncertainty in population terms, query effects, predictor effects, and pooling,
and returns posterior draws rather than only a summary.

It persists:

- `full_bayes_inference_data.nc` with posterior, sample statistics, observed
  data references, and prior/posterior predictive groups;
- `full_bayes_diagnostics.json`;
- `prior_predictive_diagnostics.json`;
- `posterior_predictive_diagnostics.json`;
- `query_posterior_summary.parquet`; and
- sensitivity summaries for robust query effects and nonlinear query length.

Intervals are labeled `posterior_credible_interval`.

## Shared posterior table

Each estimator produces exactly one row per modeled query. Separate-stratum
runs carry the stratum in their manifest and run ID. The exact column order and
machine types live in
[`schemas/query-posteriors.schema.json`](schemas/query-posteriors.schema.json);
the two estimators use that same schema.

| Column | Meaning |
|---|---|
| `run_id` | Opaque run ID |
| `query_id` | Opaque query ID |
| `estimator` | `empirical_bayes` or `full_bayes` |
| `interval_kind` | `plug_in_eb_interval` or `posterior_credible_interval` |
| `n_control`, `y_control` | Canonical control counts |
| `n_treatment`, `y_treatment` | Canonical treatment counts |
| `raw_rate_control`, `raw_rate_treatment`, `raw_delta` | Unpooled randomized summaries |
| `token_count` | Pre-treatment versioned token count |
| `query_length_log1p` | Unstandardized transformed length |
| `query_length_z` | Shared standardized transformed length |
| `p_control_mean`, `p_control_median` | Control probability summaries |
| `p_treatment_mean`, `p_treatment_median` | Treatment probability summaries |
| `delta_mean`, `delta_q50` | Gross probability difference |
| `tau_mean`, `tau_q50` | Cost-adjusted difference or null |
| `p_delta_gt_0` | Posterior/conditional posterior probability |
| `p_tau_gt_0` | Net-positive probability or null |
| `delta_q25`, `delta_q75`; `delta_q10`, `delta_q90`; `delta_q025`, `delta_q975` | Central 50%, 80%, and 95% intervals |
| Corresponding `tau_...` fields | Net intervals, or null when cost is not configured |
| `prior_mean_control`, `prior_mean_treatment` | Length-conditioned population means |
| `prior_concentration_control`, `prior_concentration_treatment` | EB effective prior sample sizes; null if not defined |
| `shrinkage_weight_control`, `shrinkage_weight_treatment` | Defined estimator-specific weights |
| `posterior_sd_delta` | SD of gross-effect draws |
| `mcse_delta_mean` | Draw Monte Carlo error; zero only for analytic EB quantity |
| `mcse_p_delta_gt_0` | Monte Carlo error of sign probability |
| `traffic_weight`, `expected_traffic_weighted_net_value`, `expected_regret_if_scored` | Prespecified traffic/value fields; regret is null until decision scoring |
| `support_status`, `overlap_status` | Randomized/query-length support labels |
| `convergence_status`, `predictive_status`, `diagnostic_status` | `PASS` or stable blocked/review codes |
| `decision_status` | `not_scored` unless approved policy scoring ran |
| `cost_mode`, `cost_outcome_units` | Explicit net-effect configuration or null |
| `model_spec_version`, `shadow_policy_version`, `canonicalization_version`, `tokenizer_version`, `outcome_definition_version`, `analysis_window_id` | Immutable provenance |

Central equal-tailed intervals are the default summary; another interval type
requires a contract version.

All probability fields MUST lie in `[0, 1]`, all effect fields in `[-1, 1]`
before optional cost subtraction, and nested intervals MUST be monotone:
50% inside 80% inside 95%.

## Comparison outputs

`compare_estimators.py` joins on the full query key and fails if either side is
missing or counts/features differ. It writes:

- `combined_query_posterior_summary.parquet`, the two shared tables stacked;
- `estimator_comparison.parquet`, one aligned row per query;
- `aggregate_reconciliation.json`;
- `sensitivity_comparison.json`;
- `comparison_diagnostics.json`; and
- `model_card.md`, containing no production query IDs or query-level values.

The aligned comparison includes:

- EB minus full-Bayes posterior mean for each arm, `delta`, and `tau`;
- ratio and difference of 50%, 80%, and 95% interval widths;
- absolute difference in sign probabilities;
- whether posterior mean signs differ;
- whether configured probability or expected-value tiers differ;
- EB bootstrap versus plug-in sensitivity;
- length and traffic support bands; and
- stable review flags.

Disagreement is reported, not hidden by rounding. A material disagreement under
the prespecified gate yields `BLOCKED_COMPARISON` until reviewed; the tool MUST
NOT automatically select the more favorable estimator.

## Aggregate reconciliation

The comparison stage computes from canonical counts:

1. the prespecified design-based aggregate treatment-control difference and
   uncertainty using randomized assignment;
2. the traffic-weighted modeled aggregate effect from each estimator; and
3. posterior/predictive intervals for the modeled aggregates.

Weights and the target population are recorded. A failure of the reconciliation
gate blocks policy scoring and is never repaired by changing weights after
looking at results.

## Policy proposal output

When, and only when, the `decision_policy` section of the versioned run
configuration is complete and approved, policy scoring may produce:

- `static_policy_proposal.parquet`;
- `probation_holdback.parquet`;
- `decision_audit.json`; and
- `proposal_README.md`.

Allowed proposal tiers are `retain`, `remove_candidate`, and
`probation_holdback`. They are proposals, not actions. Every row includes the
model run, decision-configuration fingerprint, expected traffic-weighted net
value, posterior risk, capacity contribution, reason code, and expiration
date. The scorer refuses queries outside randomized support or with failed
diagnostics.

No file is named `allowlist.csv`, and no command publishes or applies the
proposal.

## Run state and safe publication

The state machine is:

```text
NOT_STARTED -> RUNNING -> COMPLETE
                    \--> BLOCKED
                    \--> ERROR
```

`COMPLETE`, `BLOCKED`, and `ERROR` are terminal for a run ID. A rerun gets a
new run ID.

Every stage status has:

```json
{
  "schema_version": "query_level_bayes.stage_status.v1",
  "run_id": "r_opaque",
  "stage": "full_bayes",
  "state": "BLOCKED",
  "reason_codes": ["FULL_BAYES_DIVERGENCES"],
  "messages": ["Redacted aggregate diagnostic message"],
  "input_fingerprints": {},
  "config_fingerprint": "sha256",
  "started_at_utc": "timestamp",
  "finished_at_utc": "timestamp",
  "artifacts_published": false
}
```

Restricted runs use:

```text
OUTPUT_ROOT/
  status/
    RUN_ID.STAGE.json
  .staging/
    RUN_ID.STAGE.random/
  completed/
    RUN_ID/
      STAGE/
      COMPLETED
  latest/
    STAGE
```

Requirements:

- Validate that `OUTPUT_ROOT` is approved, absolute, owner-controlled, and
  outside Git before creating staging.
- Write all query-level artifacts under a fresh `.staging` directory with
  owner-only permissions.
- Validate checksums and diagnostics, then atomically rename the stage into
  `completed`.
- Create `COMPLETED` last.
- Update a `latest` pointer atomically only after `COMPLETED` exists.
- On `BLOCKED` or `ERROR`, never create `COMPLETED` or update `latest`.
- Status files contain no query IDs, row values, query-level estimates, local
  sensitive paths, credentials, or stack traces.
- An output-write or permission failure is `BLOCKED_OUTPUT_SAFETY`, not a
  partially successful run.

Synthetic runs may write under this package's ignored temporary test directory,
but committed fixtures and expected outputs MUST be demonstrably synthetic.

## Stable blocked stages

At minimum:

- `BLOCKED_PREREQUISITE`
- `BLOCKED_DATA_CONTRACT`
- `BLOCKED_DATA_PRIVACY`
- `BLOCKED_EB_FIT`
- `BLOCKED_EB_DIAGNOSTICS`
- `BLOCKED_FULL_BAYES_FIT`
- `BLOCKED_FULL_BAYES_DIAGNOSTICS`
- `BLOCKED_PREDICTIVE_CHECK`
- `BLOCKED_CALIBRATION`
- `BLOCKED_COMPARISON`
- `BLOCKED_AGGREGATE_RECONCILIATION`
- `BLOCKED_DECISION_CONFIG`
- `BLOCKED_OUTPUT_SAFETY`

Each blocked state carries one or more finer reason codes defined in the data
and acceptance contracts.
