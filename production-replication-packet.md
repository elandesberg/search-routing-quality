# Replication packet — routing design analysis on production data

Companion to the framing doc ("Compared to What?"). The goal: replace the toy
worlds' invented parameters with production estimates, rerun the same analyses, and
come back with a concrete recommended design (uncertainty set, ε, δ, cadence) and
calibrated versions of the doc's figures.

Files in this packet:

| File | What it is | Backs |
|---|---|---|
| `routing_sim.py` | ε-exploration world: naive-contrast bias, broad-vs-narrow learning curves | Doc Part Seven (Figs A, B) |
| `batch_allowlist_sim.py` | Batch A/B world: sparsity, pruning rules, expansion ranking | Doc Part Eight (Figs C, D) |
| `allowlist_model_pymc.py` | **The estimator to run in production** (PyMC/NUTS, real diagnostics). Syntax-checked but not executed in the authoring sandbox (no PyMC there) — its `--demo` cross-check against the Gibbs sampler is mandatory before first production use | Stage 2b runs on real logs |
| `hier_bayes_allowlist.py` | Model spec + validated custom Gibbs sampler (authored where no PPL was installable). Roles now: cross-check for the PyMC version, fallback where PyMC is absent, Gaussian-EB first pass (`fit_eb`), and one recorded negative result (`fit_eb_t`) | Stage 2b cross-check |

The simulation's *shapes* are the argument; this packet exists to find out whether
the shapes survive contact with our actual traffic, and what the dials should be.

---

## Stage 0 — Ground rules

- Work on aggregates and samples; no row-level customer data leaves the analysis
  environment, and nothing retailer-identifiable goes into the public doc.
- Every quantity below gets recorded in a single `calibration.yaml` so the sim run
  is reproducible and reviewable.
- Where a quantity is unknowable today (anything requiring off-allowlist treated
  traffic), record it as UNKNOWABLE, not as an estimate. Producing that list is
  itself a deliverable — it is the doc's identification argument in table form.

## Stage 1 — Calibration pulls

From production logs and billing, estimate:

| Parameter | Sim constant | Notes |
|---|---|---|
| Search sessions per week (by retailer tier if very skewed) | `WEEKLY` | |
| Baseline conversion per search session | `p0` level | overall + by broad query class |
| Allowlist share of query volume | `HEUR_Q` | share of impressions, not distinct queries |
| Incremental serving cost per enhanced query, converted to conversion-equivalent units | `COST` | state the $-to-conversion conversion rate used |
| Latency delta of the enhanced path (p50/p95) | (enters effect priors) | |
| Observed lift on allowlisted queries from any past experiment or holdout | anchor for `delta` scale | if none exists, say so — it means even the allowlist's effect is currently unmeasured |
| Candidate query features available at serve time | `phi` | embeddings + interpretable attributes; note serve-time latency budget for computing them |
| Proposed uncertainty-set definitions (2–3 candidates) and their traffic shares | `U` bounds | e.g. "all non-navigational, non-exact-SKU queries" |

## Stage 2 — Reproduce the bias demonstration on real logs

1. Compute the naive contrast on current logs: outcome for allowlisted (treated)
   traffic vs everything else, on the doc's metric tiers.
2. Adjust on observables (query class, length, intent signals, shopper segment) —
   regression or matching, analyst's choice.
3. Report naive vs adjusted vs (if a past experiment exists) experimental estimates
   for the allowlist. The spread between these three numbers is the production
   version of Figure A. Do NOT present the adjusted number as the truth — the doc's
   argument is that no adjustment recovers it; the point of this stage is to show
   how much the number moves when you try.

## Stage 2b — Batch-mode fit on the current A/B (do this first; needs no new serving infra)

If a user-level A/B with routing-on vs routing-off is running (or ran recently),
the doc's Part Eight loop can start immediately:

1. Confirm or add the **shadow allowlist flag** in the control arm (log
   would-have-been-routed for every control impression). If historical logs lack
   it, reconstruct membership from allowlist version history.
2. Build per-query contrasts on allowlisted queries: sessions, conversions by arm,
   Δ̂(q), variance. Report the sparsity profile: distribution of per-query n, share
   of queries individually powered for the doc's reference effect size (expect ~1%).
3. Fit the partial-pooling model. Implementations, in order of use:
   - **First pass:** Gaussian EB two-stage (`fit_eb` in `hier_bayes_allowlist.py`;
     same logic inline in `batch_allowlist_sim.py`). Cheap, transparent.
   - **Production estimator:** `allowlist_model_pymc.py` — the hierarchical model
     in PyMC (binomial likelihood on the logit scale, feature-model prior mean,
     non-centered Student-t random effects with continuous ν, NUTS). Before first
     production use, run its `--demo` cross-check, which fits the same synthetic
     world with both PyMC and the custom Gibbs sampler and prints decision
     agreement (require ≥ 95%, consistent σ_u and ν). Then
     `python3 allowlist_model_pymc.py --data logs.csv --cost <c>` →
     `posteriors_pymc.csv` with per-query τ mean/sd, P(net<0), keep/watch/probation.
     Acceptance bars, enforced in-script: max R-hat < 1.01, min bulk-ESS > 400,
     zero divergences (raise `target_accept` if violated). For 20k+ queries use
     `nuts_sampler="numpyro"`/`nutpie` or fewer draws.
   - **Fallback / cross-check:** the custom Gibbs sampler
     (`hier_bayes_allowlist.py --data ...`) — same model, validated in the
     authoring sandbox, no dependencies beyond numpy/scipy. Two chains, ≥ 95%
     decision agreement.
   Guidance from the head-to-heads on the synthetic world (`--demo`), which tested
   three estimators:
   - Both EB and full Bayes beat raw estimation by an order of magnitude and land
     close to each other on total value. **Use Gaussian EB as the first pass**
     (transparent, instant), **and the MCMC as the standard second pass** — it is
     cheap at this scale (seconds per chain at 2k queries, scaling linearly), nets
     somewhat more pruning value, handles genuine outlier queries better, and its
     fitted ν is a free diagnostic: ν ≈ 2–3 means some queries truly deviate from
     their type, i.e. the features are missing signal — distrust model-ranked
     expansion in proportion.
   - **A middle rung was tested and failed**: the robust-IRLS t-approximation
     (`fit_eb_t`, kept in the file as a recorded negative result) catches fewer
     outliers than plain EB at double the false-removal share, because
     residual-based downweighting cannot tell "genuinely deviant" from "noisily
     measured." Do not ship it.
   - Full Bayes is *most* valuable where hyperparameter uncertainty is material:
     small per-retailer lists (hundreds of queries), the first cycle before σ_u is
     pinned down, and any future Thompson-sampling layer. At large query counts,
     EB and Bayes converge except on outliers.
   - Neither model's P(net<0) should be treated as exactly calibrated under
     real-world model mismatch: validate the chosen threshold's realized
     false-removal rate on the next cycle's data and adjust.
4. Deliver three lists with posterior summaries: prune-to-probation candidates
   (P(net<0) > threshold — agree the threshold with the team, 0.8 is the sim's
   default), expansion candidates ranked by f̂(φ) with a support/similarity flag,
   and a small random add set. Plus the calibration read: σ̂_u (how much effect
   variation features do NOT explain — this bounds how far model-ranked expansion
   can be trusted).
5. Validation is next cycle's data: additions self-validate; removals only if
   demoted to probation rather than zeroed. State this in the deliverable.

## Stage 3 — Power and design table

For each candidate uncertainty set × ε ∈ {0.5%, 1%, 2%, 5%} × holdback δ ∈ {2%, 5%, 10%}:

- expected enhanced-query volume added per week (= traffic share × ε), and its cost
  in $ and in latency-affected sessions;
- expected treated observations per week overall and within the top ~10 query
  classes;
- minimum detectable effect on τ per class after 2, 4, 8 weeks (binomial variance,
  α = 0.05, power 0.8), at session level;
- weeks until the *policy-level* value difference (learned vs status quo) would be
  detectable in the visitor-layer A/B, under optimistic / neutral / pessimistic
  effect-surface priors anchored to Stage 1.

Output: one table, with a recommended (U, ε, δ) row and one paragraph of rationale.

## Stage 4 — Rerun the simulation, calibrated

In `routing_sim.py`, replace the world functions (`p0`, `delta`, `heur`) and the
constants block with Stage 1 values. The effect surface `delta` is the one thing
production data cannot give you off-allowlist (that is the doc's point), so run a
sweep: optimistic / neutral / pessimistic surfaces, all anchored to the on-allowlist
lift from Stage 1 and to plausible tail behavior. Keep:

- the equal-budget broad-vs-narrow comparison (this is the decision the figure
  informs);
- the support rule (policies act only where their design explored);
- the allowlist holdback;
- ≥ 20 replications, medians + IQR.

Deliver recalibrated versions of Figure A and Figure B with the same visual
grammar, clearly labeled "calibrated simulation," plus the sensitivity of the
week-8 headroom-captured number across the three effect surfaces.

## Stage 5 — Live-phase harness spec (build once exploration launches)

- Logging schema per explore-arm impression: `(session_id, query features φ(x),
  e(x), realized W, session outcome, timestamp, retailer)`. e(x) is mandatory —
  see the doc's "log the propensity" section.
- Weekly refit job: T-learner or preferred effect model on cumulative logs with
  IPW weights; export τ̂ model + its support region.
- Off-policy evaluation: IPS and doubly-robust value estimates for any candidate
  policy against the logs, with bootstrap CIs; candidates must beat the incumbent
  off-policy before promotion to a live slice.
- Promotion ladder: off-policy pass → small live slice → full explore arm; ε floor
  never below the agreed minimum.
- Guardrail monitors and automatic halt thresholds (fill from the doc's guardrail
  FILL slots once specified).

## Deliverables checklist

- [ ] `calibration.yaml` + list of UNKNOWABLE quantities
- [ ] Stage 2 memo: naive vs adjusted (vs experimental) on real logs
- [ ] Stage 3 design table + recommended (U, ε, δ)
- [ ] Stage 4 calibrated figures + sensitivity paragraph
- [ ] Stage 5 harness spec sized to our stack
- [ ] One-page summary: what changed vs the toy world, what held
