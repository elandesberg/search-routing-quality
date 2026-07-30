# Data contract

This contract is normative. `MUST`, `MUST NOT`, `SHOULD`, and `MAY` have their
usual requirements-language meanings. A run that cannot prove a `MUST` is
`BLOCKED`; it is not allowed to guess, silently drop rows, or substitute a
different estimand.

The first release accepts either:

1. event-level binary outcomes from which the implementation builds the
   canonical count table; or
2. a pre-aggregated canonical count table plus an approved aggregation audit.

Production data remains inside an approved restricted environment. Only
synthetic fixtures may be committed to this public work package.

## Identification invariant

The primary analysis population is:

> first shadow-trigger-positive query records for randomized units whose query would trigger
> AIO under one versioned shadow policy evaluated identically in treatment and
> control.

For query \(q\), the gross estimand is

\[
\Delta_q =
P(Y=1\mid Z=1,S=1,Q=q)
-
P(Y=1\mid Z=0,S=1,Q=q),
\]

where `assignment` \(Z\) is randomized assignment and
`would_trigger_aio_shadow` \(S\) is an assignment-invariant, pre-treatment
shadow-policy result. Actual AIO delivery is not \(S\).

The following rules are hard gates:

- The exact same shadow-policy artifact, canonicalization, inputs, and logic
  MUST be run for both arms.
- The shadow policy MUST NOT read assignment, actual AIO delivery, fallback
  success, clicks, the outcome, later-query behavior, or any other
  post-assignment consequence.
- Control rows without an evaluated shadow result MUST NOT be imputed from
  treatment behavior.
- Actual delivery MAY be retained as a compliance diagnostic, but MUST NOT
  select the primary analysis population or replace randomized assignment.
- For user-level randomization, retain shadow-trigger-positive opportunities
  first, then select the user's earliest such query by a deterministic,
  outcome-blind rule. The prerequisite audit MUST also establish that no prior
  experimental AIO exposure could have affected that query.
- Later queries MAY appear only in a separately labeled sensitivity analysis.
- Each modeled query MUST have positive randomized support in both arms after
  applying the primary selection rule and `would_trigger_aio_shadow == 1`.
- Query length can improve partial pooling only inside randomized support. It
  MUST NOT be presented as identifying effects for never-randomized or
  off-trigger queries.

If any rule above cannot be demonstrated, the run state is
`BLOCKED_PREREQUISITE`.

## Required analysis manifest

Every input is accompanied by `analysis_manifest.json` with schema version
`query_level_bayes.analysis_manifest.v1`. Boolean claims in the manifest are
not sufficient by themselves: each approval includes a non-sensitive evidence
reference that a human reviewer can inspect in the secure environment.

Required shape:

```json
{
  "schema_version": "query_level_bayes.analysis_manifest.v1",
  "data_classification": "synthetic",
  "dataset_id": "d_opaque",
  "experiment_id": "x_opaque",
  "experiment_window": {
    "start_utc": "2026-01-01T00:00:00Z",
    "end_utc": "2026-01-08T00:00:00Z"
  },
  "randomization": {
    "unit": "user",
    "control_value": 0,
    "treatment_value": 1,
    "assignment_probability": 0.5,
    "assignment_source_version": "assignment-v1",
    "assignment_is_immutable": true,
    "one_probability_across_retained_cohort": true,
    "health_check_approved": true,
    "evidence_ref": "secure:audit/randomization"
  },
  "selection": {
    "eligibility_version": "eligibility-v1",
    "primary_record_rule": "first_shadow_trigger_positive_query",
    "deterministic_tie_break_version": "tie-break-v1",
    "first_shadow_trigger_positive_selection_verified": true,
    "no_prior_experimental_exposure": true,
    "evidence_ref": "secure:audit/selection"
  },
  "shadow_trigger": {
    "policy_version": "shadow-aio-v1",
    "artifact_sha256": "hex-digest",
    "evaluated_in_both_arms": true,
    "assignment_invariant": true,
    "uses_only_pre_treatment_inputs": true,
    "evidence_ref": "secure:audit/shadow-trigger"
  },
  "query_identity": {
    "canonicalization_version": "canonical-query-v1",
    "opaque_id_version": "query-id-v1",
    "mapping_retained_outside_output": true,
    "evidence_ref": "secure:audit/query-identity"
  },
  "query_length": {
    "definition": "token_count",
    "tokenizer_version": "tokenizer-v1",
    "source_is_pre_treatment_canonical_query": true,
    "transform": "standardized_log1p",
    "evidence_ref": "secure:audit/query-length"
  },
  "outcome": {
    "outcome_id": "binary-outcome-v1",
    "definition_version": "outcome-definition-v1",
    "attribution_window": "prespecified value",
    "maturity_lag": "prespecified value",
    "binary": true,
    "fully_mature": true,
    "evidence_ref": "secure:audit/outcome"
  },
  "strata": {
    "mode": "none",
    "stratum_definition_version": null,
    "handling_approved": true,
    "evidence_ref": "secure:audit/strata"
  },
  "input": {
    "kind": "event_v1",
    "content_sha256": "hex-digest",
    "row_count": 1000
  }
}
```

For restricted data, `data_classification` is `restricted_production`.
Timestamps may describe the experiment window in the manifest, but query-level
timestamps MUST NOT be copied to model outputs.

Allowed `randomization.unit` values are `user`, `session`, and
`query_opportunity`. A new unit requires a contract version change.
`analysis_unit_id` identifies the randomized unit and assignment MUST be
constant within it. This aggregate-count release requires one assignment
probability across the retained cohort. Variable-propensity or blocked designs
need a separately approved event-level/design-adjusted extension and MUST NOT
be reduced to the unweighted query counts here.

For `session` or `query_opportunity` randomization, `user_cluster_id` is
required and `eligible_order` MUST impose one deterministic order across that
user's opportunities/sessions. Retain only the earliest
shadow-trigger-positive contribution per user. Repeated selected contributions
from one user are `BLOCKED_UNSUPPORTED_REPEATED_USER`; this release does not
pretend that aggregate binomial counts preserve cluster uncertainty.

`strata.mode` is one of:

- `none`; or
- `separate_fit`, meaning separate, clearly labeled count files and fits are
  made for each approved stratum.

Rows from distinct required strata MUST NOT be silently pooled.

## Opaque identifier requirements

No accepted input or output may contain query text, customer identifiers,
retailer names, account names, email addresses, URLs, or reversible encodings
of them.

- A restricted-production `query_id` MUST match
  `q_[A-Za-z0-9_-]{16,128}`. The committed synthetic fixture alone may use
  sequential `q_[0-9]{4}` labels so its contents are visibly artificial.
- `analysis_unit_id` MUST match `u_[A-Za-z0-9_-]{16,128}`.
- A non-null `user_cluster_id` MUST match `c_[A-Za-z0-9_-]{16,128}`.
- `event_id` MUST match `e_[A-Za-z0-9_-]{16,128}`.
- A non-null `stratum_id` MUST match `s_[A-Za-z0-9_-]{8,128}`.
- IDs MUST be stable within a dataset and domain-separated so a user ID cannot
  equal a query ID.
- IDs MUST be created inside the secure boundary with an approved keyed or
  otherwise non-reversible mapping. Unsalted hashes of query text are not
  acceptable.
- Mapping keys and lookup tables MUST NOT enter this work package, logs, model
  artifacts, or Git history.

The validator checks syntax, uniqueness where required, and cross-column
domain separation. The prerequisite audit records the human privacy approval
for the mapping process. Failure is `BLOCKED_DATA_PRIVACY`.

## Event input: `event_v1`

The event file is Parquet or CSV with one row per eligible query opportunity.
Parquet is preferred for restricted data. Column names and meanings are fixed:

| Column | Type | Required | Constraint |
|---|---|---:|---|
| `event_id` | string | yes | Opaque, non-null, globally unique in the input |
| `analysis_unit_id` | string | yes | Opaque randomized-unit ID |
| `user_cluster_id` | string | conditional | Required for session/query-opportunity assignment; one selected contribution per ID |
| `query_id` | string | yes | Opaque canonical query ID |
| `assignment` | int8 | yes | Exactly `0` or `1`; immutable within randomized unit |
| `assignment_probability` | float64 | yes | Finite, strictly between 0 and 1, and one value across the retained cohort |
| `randomization_block_id` | string | no | Diagnostic only; differing propensities by block are unsupported in this release |
| `eligible_order` | int64 | yes | Positive order within user (or within `analysis_unit_id` when the unit is user) |
| `is_first_shadow_trigger_positive` | bool | yes | True only for the earliest `S=1` row under the approved tie-break |
| `would_trigger_aio_shadow` | int8 | yes | Exactly `0` or `1`, evaluated for both arms |
| `shadow_policy_version` | string | yes | One value, equal to manifest version |
| `canonicalization_version` | string | yes | One value, equal to manifest version |
| `tokenizer_version` | string | yes | One value, equal to manifest version |
| `query_token_count` | int64 | yes | Positive; invariant for a `query_id` |
| `outcome` | int8 | yes | Exactly `0` or `1`; no fractional or repeated count |
| `outcome_mature` | bool | yes | Must be true for every primary row |
| `outcome_definition_version` | string | yes | One value, equal to manifest version |
| `stratum_id` | string | conditional | Required unless `strata.mode == "none"` |
| `actual_aio_delivered` | int8 | no | Diagnostic only; exactly `0` or `1` when present |

Additional columns are rejected by default. A versioned allowlist in the
analysis configuration MAY permit non-sensitive diagnostic columns, but the
model builder MUST explicitly select contract columns rather than pass through
an arbitrary frame.

### Event invariants

The builder MUST verify all of the following before reading outcome values for
modeling:

1. manifest and file fingerprints match;
2. IDs and versions satisfy this contract;
3. each `event_id` is unique;
4. assignment is constant within `analysis_unit_id` and assignment probability
   has one value across the retained cohort;
5. `eligible_order` is unique within `analysis_unit_id` for user randomization
   and within `user_cluster_id` for session/query-opportunity randomization; the
   first shadow-trigger-positive row is the minimum `S=1` order under the
   approved user-level tie-break;
6. for user randomization, exactly one first-shadow-trigger-positive primary
   record exists per user and the no-prior-exposure prerequisite is approved;
   for session/query-opportunity randomization, selected `user_cluster_id`
   values are unique;
7. the same shadow artifact/version is present in both arms and the shadow
   result is non-null on every eligible row;
8. query token count and query identity versions are invariant within
   `query_id`;
9. the outcome is binary, mature, non-null, and uses one definition version;
10. required strata are non-null and handled according to the manifest.

The primary cohort is then constructed in this exact order:

1. retain `would_trigger_aio_shadow == 1`;
2. choose the earliest retained record per `analysis_unit_id` for user
   randomization, or per `user_cluster_id` for session/query-opportunity
   randomization;
3. verify outcome maturity;
4. when `strata.mode == "separate_fit"`, select the one manifest-declared
   stratum for this run, then group by `query_id` and randomized assignment;
5. count rows as trials and sum the binary outcome as successes;
6. pivot into the canonical count schema;
7. retain queries with positive support in both arms;
8. record excluded-query counts by reason without logging query IDs;
9. compute the query-length transform from unique retained queries.

The implementation MUST NOT filter on `outcome`, `actual_aio_delivered`, a
fallback field, or any downstream event at any step.

If preselected event input contains only first-shadow-trigger-positive rows, the secure
aggregation audit MUST independently establish that earlier eligible rows were
not omitted incorrectly. Without that evidence, the run is blocked.

## Aggregate input: `query_counts_v1`

The canonical model input has one row per `query_id`. It uses wide binary
counts so both arms are visible on every row. When strata require separate
fits, each file contains exactly one approved stratum and the stratum/version
is recorded in the manifest and run ID.

| Column | Type | Required | Constraint |
|---|---|---:|---|
| `query_id` | string | yes | Opaque and unique |
| `n_control` | int64 | yes | Integer greater than zero |
| `y_control` | int64 | yes | Integer, `0 <= y_control <= n_control` |
| `n_treatment` | int64 | yes | Integer greater than zero |
| `y_treatment` | int64 | yes | Integer, `0 <= y_treatment <= n_treatment` |
| `token_count` | int64 | yes | Positive and invariant for `query_id` |
| `traffic_weight` | float64 | yes | Prespecified, positive, and normalized to sum to one |
| `cost_outcome_units` | float64 or null | yes | Finite and nonnegative when configured; contract below |

Counts MUST be unweighted counts of mature binary outcomes from primary
records. Frequencies, rates, inverse-probability weights, effective sample
sizes, and rounded values are not valid substitutes. The source audit for
aggregate input MUST attest that the event invariants and ordered aggregation
above were executed. It MUST report, by arm and only in aggregate:

- source rows;
- randomized units;
- selected primary rows;
- shadow-trigger-positive rows;
- mature outcome rows;
- retained queries;
- queries excluded for missing one arm; and
- the four final sums `n_control`, `y_control`, `n_treatment`,
  `y_treatment`.

The implementation recomputes all possible aggregate checks and refuses an
aggregate table whose totals disagree with its audit.

### Cost field

Gross lift is always estimated. Net lift is
`tau = delta - cost_outcome_units`.

One of these modes MUST be explicitly recorded:

- `per_query`: every row has a prespecified, non-outcome-derived cost;
- `constant`: the configuration supplies one prespecified constant; or
- `not_configured`: all net-effect fields and policy outputs remain null.

Zero cost is not an implicit default. It is valid only when a human explicitly
approves `constant: 0`. Cost values and their conversion to probability units
MUST be defined without using the modeled outcome.

## Query-length feature

The only group-level predictor in the first release is a versioned,
pre-treatment token count of the canonical query:

\[
\ell_q=\log(1+\text{token\_count}_q),\qquad
z_q=(\ell_q-\bar\ell)/s_\ell.
\]

Implementation requirements:

- Compute `token_count` before outcome inspection using the manifest's
  canonicalization and tokenizer versions.
- Fit \(\bar\ell\) and sample standard deviation \(s_\ell\) once, unweighted,
  over unique retained `query_id` values. Do not traffic-weight the transform
  and do not count a query more than once because it appears in several strata.
- Require at least two distinct finite \(\ell_q\) values and \(s_\ell>0\).
- Persist `n_unique_queries`, mean, sample standard deviation, minimum,
  maximum, canonicalization version, and tokenizer version in
  `feature_transform.json`.
- Apply exactly the same stored transform to EB, full Bayes, sensitivities,
  and comparisons.
- Reject a supplied standardized feature unless recomputation matches within
  `1e-12` absolute tolerance.
- Flag predictions outside the retained raw token-count range as
  `outside_randomized_length_support`; they cannot enter primary estimates or
  policy proposals.

Interactions with assignment are model terms, not new post-treatment
features. The feature transform MUST NOT be refit separately by arm.

## Missingness and exclusions

There is no silent imputation in the first release.

- Missing assignment, query ID, shadow trigger, outcome, token count, version,
  or required stratum blocks the dataset.
- Immature outcomes block the dataset; they are not treated as failures.
- A query with no retained observations in one arm is excluded from
  query-level modeling and reported only as an aggregate exclusion count.
- If exclusions remove all queries or a required stratum, the run is blocked.
- Outcome-dependent exclusions are forbidden.

Every exclusion rule is prespecified and produces an aggregate reason count.
No validation message may print a production `query_id` or
`analysis_unit_id`.

## Data audit output

Successful validation produces `data_audit.json` with:

- schema and contract versions;
- input and manifest fingerprints;
- all aggregate flow counts above;
- per-arm outcome totals and raw rates;
- positive-support query count;
- query-count and traffic quantiles;
- token-count range and transform parameters;
- strata counts;
- duplicate and missing-value counts, all zero where required;
- explicit confirmation that actual delivery was not used for selection; and
- `state: "PASS"`.

A blocked validation produces only a redacted status record described in
`INTERFACES.md`; it MUST NOT leave a canonical count file or a completed-run
marker.

## Safe handling

- Restricted input and output paths MUST be absolute, explicitly configured,
  and outside every Git worktree.
- Directories MUST be owner-only (`0700`) and files owner-only (`0600`) unless
  a stricter approved control applies.
- Validators and exception messages MUST report counts and contract fields,
  not row contents or IDs.
- Temporary model data, posterior draws, and query summaries receive the same
  classification as the source data.
- A run writes to a fresh staging directory and publishes atomically only
  after all required gates pass.
- On any blocked prerequisite, validation failure, model failure, diagnostic
  failure, or write failure, staging is quarantined or removed according to
  the secure retention policy and no `COMPLETED` marker or `latest` pointer is
  written.
- Raw query text, ID mappings, credentials, signed URLs, and production
  query-level artifacts MUST never be committed, attached to an issue, or
  included in a public release.

## Data block reason codes

At minimum, implementations emit these stable codes:

- `PREREQ_RANDOMIZATION_UNAPPROVED`
- `PREREQ_SHADOW_NOT_BOTH_ARMS`
- `PREREQ_SHADOW_NOT_ASSIGNMENT_INVARIANT`
- `PREREQ_SHADOW_VERSION_MISMATCH`
- `PREREQ_FIRST_ELIGIBLE_UNVERIFIED`
- `PREREQ_PRIOR_EXPOSURE_NOT_EXCLUDED`
- `PREREQ_OUTCOME_NOT_BINARY`
- `PREREQ_OUTCOME_IMMATURE`
- `DATA_IDENTIFIER_NOT_OPAQUE`
- `DATA_ASSIGNMENT_INVALID`
- `BLOCKED_UNSUPPORTED_VARIABLE_PROPENSITY`
- `BLOCKED_UNSUPPORTED_REPEATED_USER`
- `DATA_PRIMARY_RECORD_INVALID`
- `DATA_SHADOW_MISSING`
- `DATA_VERSION_MISMATCH`
- `DATA_OUTCOME_INVALID`
- `DATA_QUERY_LENGTH_INVALID`
- `DATA_STRATA_UNHANDLED`
- `DATA_COUNT_NOT_INTEGER`
- `DATA_COUNT_OUT_OF_RANGE`
- `DATA_QUERY_ARM_SUPPORT_MISSING`
- `DATA_AGGREGATE_AUDIT_MISMATCH`
- `DATA_RESTRICTED_PATH_IN_GIT`

One run may contain multiple reason codes. Human-readable messages accompany
them, but automation keys only on the stable codes.
