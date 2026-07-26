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
| `allowlist_model_pymc.py` | Candidate production estimator (PyMC/NUTS, real diagnostics). The locked reduced path and fail-closed behavior are tested; its full `--demo` remains a human release gate, not proof of production validity | Stage 2b model fit |
| `synthetic_benchmarks.py` | Explicitly non-production known-truth fixture, Gaussian-EB orientation benchmark, and recorded negative robust-IRLS experiment | Stage 2b synthetic review |

The simulation's *shapes* are the argument; this packet exists to find out whether
the shapes survive contact with our actual traffic, and what the dials should be.

**Execution order:** Stage 0 → Stage 1 → the Stage 2b prerequisite audit and, only
if it passes, the batch fit → Stage 2 descriptive bias memo → Stage 3 design table
→ Stage 4 calibrated simulations → Stage 5 live harness. Stage 2b comes before the
observational memo because the randomized visitor-level result is the audited
anchor. A failed Stage 2b prerequisite is an output, not permission to improvise a
per-query causal estimate.

---

## Stage 0 — Ground rules

- Work on aggregates and samples; no row-level customer data leaves the analysis
  environment, and nothing retailer-identifiable goes into the public doc.
- Every quantity below gets recorded in a single `calibration.yaml` so the sim run
  is reproducible and reviewable.
- Where a quantity is unknowable today (anything requiring off-allowlist treated
  traffic), record it as UNKNOWABLE, not as an estimate. Producing that list is
  itself a deliverable — it is the doc's identification argument in table form.
- Freeze two estimands before touching the model:
  - **Primary policy estimand:** the visitor-level intention-to-treat difference
    between the assigned routing policy and status quo, using the agreed outcome
    window and the visitor as the randomization cluster.
  - **Primary query-learning estimand:** the treatment contrast at each visitor's
    first eligible query. Later/all-query contrasts are sensitivity analyses because
    earlier treatment can change which queries the visitor issues next.
- Write a metric contract: randomization and analysis unit, denominator, attribution
  window, delayed-outcome cutoff, censoring, repeated-session handling, and the
  exact treatment and policy versions. The supplied binomial models apply only to
  one binary outcome contribution per randomized unit; use a distribution-appropriate
  model for revenue, counts, repeated outcomes, or other non-binary metrics.

## Stage 1 — Calibration pulls

From production logs and billing, estimate:

| Parameter | Sim constant | Notes |
|---|---|---|
| Search sessions and unique randomized visitors per week | `WEEKLY` | overall + by retailer tier; estimate repeat-session clustering |
| Baseline outcome under the metric contract | `p0` level | overall + by broad query class, retailer, and time period |
| Allowlist share of query volume | `HEUR_Q` | share of impressions, not distinct queries |
| Incremental serving cost per enhanced query, converted to outcome-equivalent units if using a priced objective | `COST` | retain the dollar view; state the conversion/value rate and sensitivity, by retailer or query class where material |
| Latency delta of the enhanced path (p50/p95/p99) at current and proposed routed load | direct effect + scale check | distinguish individual delay from shared-capacity interference |
| Observed lift on allowlisted queries from any past experiment or holdout | anchor for `delta` scale | if none exists, say so — it means even the allowlist's effect is currently unmeasured |
| Candidate query features available at serve time | `phi` | embeddings + interpretable attributes; note serve-time latency budget for computing them |
| Proposed uncertainty-set definitions (2–3 candidates) and their traffic shares | `U` bounds | e.g. "all non-navigational, non-exact-SKU queries" |
| Proposed outer explore-arm share | visitor-layer allocation | required for cost and policy-level power; keep as a design choice |
| Visitor/session clustering and outcome variance | power inputs | estimate ICC/design effect or resample production visitor histories |

## Stage 2 — Reproduce the bias demonstration on real logs

1. Compute the naive contrast on current logs: outcome for allowlisted (treated)
   traffic vs everything else, on the doc's metric tiers and frozen outcome window.
2. Adjust on observables (query class, length, intent signals, shopper segment) —
   regression or matching, with overlap diagnostics and the same target population.
3. Report naive vs adjusted vs (if a past experiment exists) experimental estimates
   for the same allowlist population wherever possible. The spread between these
   numbers is the production analogue of Figure A, but its sign is not predetermined:
   baseline composition can make the naive contrast flatter, understate, or reverse
   the effect. Do NOT present the adjusted number as truth or the spread as a bias
   estimate. The point is to show sensitivity and preserve the experimental estimate
   as the causal anchor.

## Stage 2b — Batch-mode fit on the current A/B (do this first; audit existing logs before fitting)

If a user-level A/B with routing-on vs routing-off is running (or ran recently),
begin with this prerequisite audit. Do not produce per-query action lists unless all
required items pass:

1. **Randomization and policy integrity:** verify visitor-level assignment, stable
   assignment across sessions, no sample-ratio mismatch, treatment and allowlist
   versions, and the assigned policy in each arm. Report the visitor-level policy
   ITT first, with uncertainty clustered by assigned visitor.
2. **Eligibility reconstruction:** confirm the **versioned shadow allowlist flag**
   in control (would-have-been-routed at that timestamp). Historical reconstruction
   is acceptable only if allowlist version history and all serve-time gates are
   complete; otherwise mark query-level analysis BLOCKED.
3. **First-eligible cohort:** identify each visitor's first eligible query before
   this experiment could have changed later behavior. Verify that the metric joins
   once per randomization unit. Retain later/all-query records only for a labeled
   sensitivity analysis; do not treat them as independent binomial trials.
4. **Outcome and heterogeneity fit:** confirm the outcome is binary before using the
   supplied binomial likelihood. Preserve retailer and time/treatment-version strata
   wherever effects or baselines plausibly differ; do not collapse them into a
   single query count merely to fit the reference script.
5. Build first-eligible per-query or query-class contrasts: unique units, outcomes
   by arm, Δ̂(q), and cluster-aware variance. Report sparsity, effective sample size,
   and the share individually powered for the reference effect. Report the same
   profile for later/all-query sensitivity data, without calling it causal truth.
6. Fit the partial-pooling model. Implementations, in order of use:
   - **Orientation benchmark:** Gaussian EB two-stage
     (`fit_gaussian_eb` in `synthetic_benchmarks.py`; related logic appears in
     `batch_allowlist_sim.py`). Cheap and transparent, but it treats fitted
     hyperparameters as fixed. Use it to orient and debug the analysis, not as a
     second production estimator or a source of automatic actions.
   - **Candidate production estimator:** `allowlist_model_pymc.py` — the hierarchical
     model in PyMC (binomial likelihood on the logit scale, feature-model prior
     mean, non-centered Student-t random effects with prespecified ν=4 by default,
     NUTS). ν is fixed because it is weakly identified against the random-effect
     scale and is not part of the decision estimand. Before any real fit, run
     `--demo` as a diagnostic-gated synthetic check. It reports recovery
     against known truth: error, truth correlation, negative-probability Brier
     score, sign accuracy, approximate interval coverage, outlier-subset recovery,
     and candidate-ranking quality. These are descriptive diagnostics, not
     production evidence or universal pass bars. Review them against acceptance
     criteria declared for this application. Then
     `python allowlist_model_pymc.py --data logs.csv --cost <c>` →
     `posteriors_pymc.csv` with per-query τ mean/sd, continuous P(net<0), and
     explicitly non-authoritative diagnostic probability bands. The script
     hard-stops and writes no current posterior report if max R-hat ≥ 1.01, min
     bulk-ESS ≤ 400, or any divergence remains. Before a rerun, it preserves any
     prior report under a `.stale-<UTC timestamp>` name so an old result cannot
     masquerade as the current fit. Check decision-driving local effects and Monte
     Carlo error near the boundary, not hyperparameters alone, and run
     prior/posterior predictive checks. Predeclare a ν sensitivity grid (for
     example 3, 5, and 10 via `--student-df`) and treat material changes in
     decision-driving posteriors or ranks as a blocker, not a tuning opportunity.
     For 20k+ queries, use an appropriate
     sampler or model reduction; fewer draws are acceptable only if the same
     diagnostics and decision stability still pass.
   Guidance from the synthetic benchmarks:
   - The Gaussian-EB benchmark is a transparent orientation point, while PyMC is
     the only candidate production estimator and is usable only after diagnostics
     pass. Compare their known-truth recovery descriptively; do not require them to
     agree or assume either one calibrates the other. Heavy tails allow measured
     queries to depart from their type, but neither the prespecified ν nor its
     sensitivity grid quantifies off-support transport error; distrust model-ranked
     expansion until prospective validation.
   - **A middle rung was tested and failed**: the robust-IRLS t-approximation
     (`fit_robust_irls_negative_benchmark`, retained in
     `synthetic_benchmarks.py` as a recorded negative result) catches fewer outliers
     than plain EB at double the false-removal share, because
     residual-based downweighting cannot tell "genuinely deviant" from "noisily
     measured." Do not ship it.
   - Full Bayes is potentially most valuable where hyperparameter uncertainty is material:
     small per-retailer lists (hundreds of queries), the first cycle before σ_u is
     pinned down, and any future Thompson-sampling layer. At large query counts,
     EB and Bayes may converge except on outliers, but verify rather than assume.
   - Neither PyMC's P(net<0) nor the EB benchmark's approximation should be treated
     as exactly calibrated under real-world model mismatch: validate the frozen
     decision rule on next-cycle probation and addition data, by retailer and time
     where possible.
7. Turn posteriors into actions with an explicit loss/value rule. Deliver:
   - probation candidates with posterior mean/interval, P(net<0), traffic, contextual
     cost/value, expected traffic-weighted gain from demotion, and expected regret;
   - expansion candidates ranked only within measured support, with similarity/OOD
     diagnostics and the same value fields;
   - a small random or near-random add set.
   The 0.8 probability threshold is a simulation default, not a production rule.
   Derive any threshold from the relative loss of false removal and false retention,
   and account for capacity. σ̂_u describes unexplained variation on the measured
   allowlist; it does not bound extrapolation error off support.
8. Validate on next-cycle held-out data. Additions are prospectively testable;
   removals are testable only if demoted to probation rather than zeroed.

**Stage 2b outputs:** prerequisite audit with PASS/BLOCKED per item; primary
visitor-policy ITT; first-eligible sparsity and contrast table; labeled later-query
sensitivity; model diagnostics, predictive checks, and prespecified-ν sensitivity;
traffic/value/loss-aware probation, supported-expansion, and random-add lists;
next-cycle validation plan.

## Stage 3 — Power and design table

For each candidate outer explore-arm share × uncertainty set × ε ∈ {0.5%, 1%, 2%, 5%}
× holdback δ ∈ {2%, 5%, 10%}:

- expected enhanced-query volume added per week (= outer explore share × eligible
  traffic share × ε), contextual serving cost in $, and latency-affected sessions;
- expected treated observations per week overall and within the top ~10 query
  classes and priority retailer strata, plus IPW effective sample size;
- minimum detectable effect on the first-eligible query estimand after 2, 4, 8 weeks,
  using unique randomized units and visitor-cluster variance rather than a row-level
  binomial shortcut; state multiplicity and repeated-look handling;
- weeks until the *policy-level* value difference (learned vs status quo) would be
  detectable in the visitor-layer A/B, under optimistic / neutral / pessimistic
  effect-surface priors anchored to Stage 1. Power this separately from query-level
  learning, using the visitor assignment and repeat-session design effect.

Prefer re-randomization or bootstrap simulation over production visitor histories
when available. Output: one table with a recommended (outer share, U, ε, δ) row,
worst-stratum precision, and one paragraph of rationale. The outer share and
randomization granularity remain team decisions; the table informs rather than
silently resolves them.

## Stage 4 — Rerun the simulation, calibrated

In `routing_sim.py`, replace the world functions (`p0`, `delta`, `heur`) and the
constants block with Stage 1 values. The effect surface `delta` is the one thing
production data cannot give you off-allowlist (that is the doc's point), so run a
sweep: optimistic / neutral / pessimistic surfaces, all anchored to the on-allowlist
lift from Stage 1 and to plausible tail behavior. Keep:

- the equal-budget broad-vs-narrow comparison as a design tradeoff, not a universal
  theorem;
- the support rule (policies act only where their design explored);
- the allowlist holdback;
- ≥ 20 replications, medians + IQR, with Monte Carlo uncertainty adequate for the
  reported decision;
- adverse cases for weak/no feature signal, retailer heterogeneity, time drift,
  off-support shift, and nonlinear cost/latency at scale.

Deliver recalibrated versions of Figure A and Figure B with the same visual
grammar, clearly labeled "calibrated simulation," plus the sensitivity of the
week-8 headroom-captured number across the three effect surfaces.

## Stage 5 — Live-phase harness spec (build once exploration launches)

- Logging schema per decision: privacy-safe `visitor_id`, `session_id`, randomization
  unit and outer assigned arm; experiment, policy, allowlist, enhanced-model, prompt,
  and search-stack versions; query ID/order and serve-time feature snapshot; retailer
  and catalog/time context; uncertainty-set/allowlist eligibility and support flags;
  `e(x)` after every gate/override; assigned action, delivered action,
  fallback/noncompliance reason; raw latency inside the environment, realized
  serving cost, errors; outcome definition, attribution
  window, timestamp, maturity/censoring. Log both assignment and delivery. The
  propensity is mandatory and cannot be reconstructed reliably afterward.
- Weekly refit job: primary fit on first-eligible records; later/all-query sensitivity
  kept separate. Use a distribution-appropriate outcome model, retailer/time varying
  effects where supported, IPW or randomized pseudo-outcomes, and visitor-clustered
  uncertainty. Export the effect model, treatment/version target, and support region.
- Off-policy evaluation: only supported candidate policies; train and evaluate on
  different folds or time periods; use clustered IPS/self-normalized IPS and
  cross-fitted doubly robust estimates with visitor-cluster bootstrap CIs. Report
  weight tails, effective sample size, clipping sensitivity, retailer results, and
  the number of policies screened. If several query actions share one session
  outcome, use the predeclared first-eligible record or an explicitly sequential
  estimator — not ordinary one-row contextual-bandit IPS.
- Candidates must beat the incumbent by a predeclared practical margin off-policy
  before promotion, then pass the randomized live slice; OPE is a screen, not the
  audited launch decision.
- Promotion ladder: off-policy pass → small live slice → full explore arm; ε floor
  never below the agreed minimum.
- Guardrail monitors and automatic halt thresholds (fill from the doc's guardrail
  FILL slots once specified).
- Run a separate capacity/scale check for tail latency, cost, fallback, and control
  contamination. Low-volume exploration estimates direct effects at that load; it
  does not by itself identify performance after a large routing expansion.

## Deliverables checklist

- [ ] `calibration.yaml` + list of UNKNOWABLE quantities
- [ ] Stage 2b prerequisite audit + primary visitor ITT + eligible query dataset
- [ ] Stage 2 memo: naive vs adjusted (vs experimental) on real logs
- [ ] Stage 3 design table + recommended (outer share, U, ε, δ)
- [ ] Stage 4 calibrated figures + sensitivity paragraph
- [ ] Stage 5 harness spec sized to our stack
- [ ] One-page summary: what changed vs the toy world, what held
