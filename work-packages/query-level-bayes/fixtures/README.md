# Synthetic contract fixtures

These files contain invented counts and known probabilities. They are not
production evidence and must not be used to select, remove, or add queries.

`synthetic-query-counts.csv` has one row per opaque query ID. Each row represents
the first shadow-trigger-positive opportunity for randomized users in a synthetic
shadow-trigger population:

- `n_control`, `y_control`: randomized control opportunities and binary
  outcomes;
- `n_treatment`, `y_treatment`: randomized treatment opportunities and binary
  outcomes;
- `token_count`: a synthetic pre-treatment query-length input;
- `traffic_weight`: synthetic population weight, summing to one; and
- `cost_outcome_units`: synthetic serving cost expressed in the same
  probability-point units as the outcome.

`synthetic-known-truth.csv` records the probabilities used to construct the toy
world. For every row:

```text
delta_gross_true = p_treatment_true - p_control_true
tau_net_true = delta_gross_true - cost_outcome_units
```

The fixture intentionally spans positive, near-zero, and negative net effects,
as well as high- and low-traffic query IDs. IDs are opaque `q_####` labels; no
query text, customer data, or retailer information is present.

`prerequisite-audit.pass.json` is a synthetic-only example of a fully passing
prerequisite audit. A production audit needs real evidence IDs and named human
approval. Copying the fixture statuses does not authorize a production fit.

`analysis-manifest.synthetic.json` records the cohort, randomization,
shadow-policy, outcome, identity, and feature versions for the fixture.
`aggregation-audit.synthetic.json` reconciles its final arm totals. Both are
examples, not approvals or production defaults.
