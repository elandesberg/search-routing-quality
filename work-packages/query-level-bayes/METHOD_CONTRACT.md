# Method contract

This file is normative. Both estimators must use the same validated cohort,
estimand, feature transform, and output scale. A model run is invalid if any
prerequisite or diagnostic below fails.

## 1. Cohort and estimand

Let \(Z\in\{0,1\}\) be randomized assignment, not actual AIO delivery. Let
\(S=1\) mean that the versioned, pre-treatment shadow policy would have
triggered AIO. The same shadow-policy code and version must run in both arms.
Actual delivery, fallback, clicks, and later-query occurrence are
post-assignment variables and must not define the cohort.

For user-level randomization, first retain opportunities with \(S=1\), then
select each user's earliest such query by server event time and a prespecified
deterministic tie-break. Require its outcome to be mature only after selection.
It must precede any experimental AIO exposure. Later shadow-trigger-positive
queries are excluded from the primary analysis. For session or
query-opportunity randomization, an opaque user-cluster ID and deterministic
user-level query order are required; retain only that user's earliest
shadow-trigger-positive contribution. Repeated-user cluster extensions require
a separate event-level contract and are blocked here.

The aggregate-count first release also requires one assignment propensity
across the retained cohort. If propensities vary by block or unit, use a
separately approved design-adjusted/event-level extension; do not collapse
them into the unweighted counts below.

For canonical query ID \(q\),

\[
p_{qz}=P\{Y(z)=1\mid S=1,Q=q\},\qquad
\Delta_q=p_{q1}-p_{q0},\qquad
\tau_q=\Delta_q-c_q .
\]

\(Y\) is one prespecified binary outcome with a fixed, fully mature attribution
window. \(c_q\) is an optional incremental serving cost expressed in the same
probability-point value units as \(\Delta_q\). If no approved conversion exists,
\(\tau_q\) and its probabilities are missing; the implementation must not
silently set \(c_q=0\).

The query-level effect is the randomized intent-to-treat effect within the
shadow-trigger population and observed experimental support. Report gross
\(\Delta_q\) and net \(\tau_q\) separately. Do not report log-odds coefficients
as product lift.

Traffic-weighted aggregate effects use prespecified, assignment-invariant
weights \(w_q\), normalized to sum to one:

\[
\Delta_{\mathrm{traffic}}=\sum_q w_q\Delta_q,\qquad
\tau_{\mathrm{traffic}}=\sum_q w_q\tau_q .
\]

Equal-query averages are descriptive only and must be labeled as such.

## 2. Query-length feature

Query length is computed before outcomes are inspected:

\[
L_q=
\frac{\log(1+\operatorname{token\_count}_q)-\bar L}{s_L}.
\]

The canonicalization and tokenizer versions, \(\bar L\), and \(s_L>0\) are
run artifacts. The basis \(B(L_q)\) is fixed in the approved model
configuration. The first release must support a linear basis; a low-degree
natural-spline basis is the required prespecified sensitivity. Expanded
columns must be centered and scaled. An internal QR parameterization is
allowed, but reported coefficients and predictions must be transformed back
to the declared basis. No feature may depend on treatment delivery, outcomes,
or a post-assignment query.

## 3. Empirical Bayes

For observed successes \(y_{qz}\) from \(n_{qz}\) eligible randomized
opportunities,

\[
\begin{aligned}
y_{qz}\mid p_{qz}&\sim\operatorname{Binomial}(n_{qz},p_{qz}),\\
p_{qz}\mid L_q&\sim
\operatorname{Beta}\{\kappa_z\mu_{qz},\kappa_z(1-\mu_{qz})\},\\
\operatorname{logit}(\mu_{qz})
&=\alpha+B(L_q)^\top\gamma_0+
z\{\beta+B(L_q)^\top\gamma_\tau\}.
\end{aligned}
\]

Estimate \(\alpha,\beta,\gamma_0,\gamma_\tau,\log\kappa_0,\log\kappa_1\)
jointly by maximizing the beta-binomial marginal likelihood across all query
and arm cells. Use stable log-beta calculations, multiple deterministic
starts, explicit parameter bounds, and retain objective, gradient, Hessian or
profile, boundary, and optimizer-status diagnostics.

Conditional on the fitted hyperparameters,

\[
p_{qz}\mid y,\widehat\theta\sim
\operatorname{Beta}\{
y_{qz}+\widehat\kappa_z\widehat\mu_{qz},
n_{qz}-y_{qz}+\widehat\kappa_z(1-\widehat\mu_{qz})
\}.
\]

Pair independently generated arm draws conditional on \(\widehat\theta\), then
compute \(\Delta_q^{(d)}=p_{q1}^{(d)}-p_{q0}^{(d)}\) and
\(\tau_q^{(d)}=\Delta_q^{(d)}-c_q^{(d)}\). This arm-independence is an EB
limitation, not a claim that potential outcomes are independent.

Every main EB interval must have
`interval_kind=plug_in_eb_interval`: it conditions on estimated
hyperparameters and is not a full posterior credible interval. Separately
refit the entire EB model in a prespecified bootstrap. Prefer resampling
independent randomization units, clustering on user where applicable; when
only independent aggregate counts exist, use a documented parametric
beta-binomial bootstrap. Label those results
`eb_hyperparameter_sensitivity_interval`; do not substitute them silently for
the plug-in result. Write them to the separate
`schemas/eb-bootstrap-sensitivity.schema.json` contract, never to the shared
primary posterior table.

## 4. Full hierarchical Bayes

Use an arm-centered correlated hierarchical logistic model:

\[
\begin{aligned}
y_{q0}&\sim\operatorname{Binomial}
\{n_{q0},\operatorname{logit}^{-1}(m_q-b_q/2)\},\\
y_{q1}&\sim\operatorname{Binomial}
\{n_{q1},\operatorname{logit}^{-1}(m_q+b_q/2)\},\\
m_q&=\alpha+B(L_q)^\top\gamma_0+u_{0q},\\
b_q&=\beta+B(L_q)^\top\gamma_\tau+u_{\tau q}.
\end{aligned}
\]

The primary residual model is noncentered:

\[
\begin{aligned}
r_{0q},r_{\tau q}&\overset{iid}{\sim}N(0,1),\\
u_{0q}&=\sigma_0r_{0q},\\
u_{\tau q}&=\sigma_\tau\{
\rho r_{0q}+\sqrt{1-\rho^2}\,r_{\tau q}\}.
\end{aligned}
\]

Use proper, weakly informative priors from the approved model configuration:
normal priors for \(\alpha,\beta,\gamma_0,\gamma_\tau\), half-normal priors for
\(\sigma_0,\sigma_\tau\), and an \(\operatorname{LKJ}(\eta)\) prior on the
2-by-2 correlation matrix. There are no outcome-tuned prior defaults.
Production fitting is blocked until the exact location, scale, and \(\eta\)
values pass prior-predictive review.

The required robust-effect sensitivity keeps every other choice fixed and
replaces \(r_{\tau q}\) with a unit-variance Student-\(t\) residual:

\[
r_{\tau q}=
\sqrt{\frac{\nu-2}{\nu}}\,t_{\nu q},\qquad
t_{\nu q}\sim t_\nu,\qquad \nu=4.
\]

\(\nu=4\) is fixed and must not be estimated. Any alternative degrees of
freedom is a separately versioned, predeclared sensitivity.

Fit the continuous hierarchy with an HMC/NUTS-capable implementation and retain
its chain diagnostics. This work package has no Gibbs-sampler path.

For every posterior draw, derive

\[
p_{q0}=\operatorname{logit}^{-1}(m_q-b_q/2),\quad
p_{q1}=\operatorname{logit}^{-1}(m_q+b_q/2),
\]

then compute \(\Delta_q\), \(\tau_q\), and traffic-weighted aggregates on the
probability scale. Full-Bayes intervals use
`interval_kind=posterior_credible_interval`. Persist posterior draws or
InferenceData, not only summaries.

## 5. Required outputs

Both methods must emit the same query rows with:

- run, method, model-specification, shadow-policy, canonicalization, tokenizer,
  outcome, and analysis-window versions;
- opaque query ID; \(n_{q0},y_{q0},n_{q1},y_{q1}\); raw arm rates and raw
  difference; raw and standardized length; traffic weight; and approved cost;
- posterior/conditional mean and median for \(p_{q0},p_{q1},\Delta_q,\tau_q\);
- 50%, 80%, and 95% intervals with an exact `interval_kind`;
- \(P(\Delta_q>0)\) and, when cost is available, \(P(\tau_q>0)\);
- shrinkage, effective-prior/concentration, overlap, support, convergence, and
  predictive-check fields; and
- `decision_status=not_scored` unless a complete approved decision
  configuration was supplied.

Also emit traffic-weighted aggregate summaries, within-support query-length
curves, design-based-versus-modeled reconciliation, EB-versus-full-Bayes
interval/probability/value disagreements, and sensitivity deltas. Never emit
raw query text or a production query-level decision list to Git.

## 6. Diagnostics and release gates

All gates fail closed. A failed run must not leave an artifact marked current
or complete.

For EB, require finite marginal likelihood and derivatives, optimizer
convergence from repeated starts, no unreviewed concentration boundary,
leave-one-query-out or held-out predictive checks by arm, length, and traffic
band, bootstrap stability, and known-truth interval calibration.

For full Bayes, require:

- prior predictive checks before fitting and posterior predictive checks by
  arm, length, traffic band, and approved stratum;
- at least four chains, rank-normalized split \(\widehat R<1.01\), and bulk and
  tail ESS strictly greater than 400 for every hyperparameter, aggregate estimand, and
  reported local effect;
- zero divergent transitions, zero maximum-treedepth hits, and chain
  E-BFMI at least 0.30;
- Monte Carlo standard error of each reported mean at most 5% of its posterior
  standard deviation and of each decision-driving probability at most 0.01;
- simulation-based recovery and interval calibration across traffic and
  query-length bands; and
- normal-versus-fixed-\(\nu=4\) and linear-versus-spline sensitivity review.

Do not pass by dropping bad queries, raising a threshold, shortening the
model, or merely increasing `target_accept`. Reparameterize or revise the
prespecified model, rerun all checks, and version the change. Material
predictive, calibration, aggregate-reconciliation, or cross-method
disagreement uses the predeclared tolerances in `DECISIONS_REQUIRED.md` and
requires human review.

## 7. Decision boundary

Inference and action are separate stages. Without a complete approved decision
configuration containing traffic/value weights, asymmetric loss, capacity,
posterior-risk constraints, and probation/holdback rules, the scorer must
refuse to run. There is no default posterior-probability threshold and no
automatic `keep`, `remove`, or `add` action. Any scored output is a proposal
for the next operating cycle, not authorization to change routing.

## 8. Identification limits

Randomization identifies assignment effects only for \(S=1\), the recorded
policy version, the experiment window, and queries with randomized support.
These models do not identify treatment-on-treated effects, off-trigger or
never-randomized queries, effects of later treatment-selected queries,
long-run query-composition changes, capacity/interference effects, or effects
for unseen query identities. Query length improves partial pooling within
support; its smooth curve and every extrapolation are model-dependent and do
not create causal information. Observational strata, cost conversions, and
policy values require their own evidence and assumptions.
