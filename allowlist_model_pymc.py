"""Hierarchical Bayesian allowlist estimator — PyMC production implementation.

This is the package's sole candidate production estimator. It uses PyMC's
maintained NUTS implementation and fails closed on R-hat, bulk-ESS, and
divergence diagnostics. Release thresholds can be tightened but not weakened.

  c0_q ~ Binomial(n0_q, sigmoid(alpha_q))
  c1_q ~ Binomial(n1_q, sigmoid(alpha_q + b_q))
  alpha_q = Phi_q @ gamma + sigma_a * a_raw_q,   a_raw ~ Normal(0, 1)
  b_q     = Phi_q @ beta  + sigma_u * u_raw_q,   u_raw ~ StudentT(4, 0, 1)
  gamma, beta ~ Normal(0, 1);  sigma_a ~ HalfNormal(1.5);
  sigma_u ~ HalfNormal(0.3)

Non-centered parameterization throughout (avoids the funnel). Net effect per
query, on the probability scale, is computed from the posterior draws:
  tau_q = sigmoid(alpha_q + b_q) - sigmoid(alpha_q) - cost
The Student-t degrees of freedom are prespecified (4 by default) because they
are weakly identified against the random-effect scale and are not part of the
decision estimand. Use --student-df for prespecified sensitivity runs.

FIRST RUN IN ANY LOCKED ENVIRONMENT MUST BE THE SYNTHETIC CHECK:
    python3 allowlist_model_pymc.py --demo
It reports recovery against known synthetic truth and Gaussian-EB orientation
benchmarks. Those recovery metrics are descriptive: this package does not
invent a universal accuracy threshold. The only automatic gates are the
release sampler diagnostics. Owners must define application-specific
acceptance criteria before interpreting a production posterior.

USAGE
  synthetic check: python3 allowlist_model_pymc.py --demo [--outliers 0.03]
  production:   python3 allowlist_model_pymc.py --data logs.csv --cost 0.002
  Four chains run sequentially by default (--chains 4 --cores 1) for portable
  worker startup. Increase --cores only after validating the target environment;
  cores must be between 1 and the number of chains.
  logs.csv columns: query_id, n0, c0, n1, c1, f1..fK. The safe default is a
  standardized linear design with an intercept. Quadratic expansion is an
  explicit, dimension-guarded option.
"""

import argparse
import json

import numpy as np
from scipy.special import expit
from scipy.stats import rankdata

from production_io import (
    DEFAULT_MAX_BASIS_TERMS,
    DataValidationError,
    FeatureDesign,
    archive_existing_outputs,
    candidate_rows,
    load_allowlist_csv,
    load_candidate_csv,
    posterior_rows,
    support_distances,
    write_csv_atomic,
)
from synthetic_benchmarks import (
    COST,
    fit_gaussian_eb,
    fit_robust_irls_negative_benchmark,
    make_synthetic_world,
)

RELEASE_MAX_RHAT = 1.01
RELEASE_MIN_ESS = 400.0
RELEASE_MAX_DIVERGENCES = 0


class DiagnosticsError(RuntimeError):
    """Raised when a PyMC fit is not safe to export as a posterior report."""


def _validate_diagnostic_thresholds(max_rhat, min_ess, max_divergences):
    try:
        thresholds = (float(max_rhat), float(min_ess), float(max_divergences))
    except (TypeError, ValueError) as exc:
        raise ValueError("diagnostic thresholds must be finite numbers") from exc
    if (
        not all(np.isfinite(value) for value in thresholds)
        or thresholds[0] <= 0
        or thresholds[1] < 0
        or thresholds[2] < 0
    ):
        raise ValueError("diagnostic thresholds must be finite and nonnegative")
    if (
        thresholds[0] > RELEASE_MAX_RHAT
        or thresholds[1] < RELEASE_MIN_ESS
        or thresholds[2] > RELEASE_MAX_DIVERGENCES
    ):
        raise ValueError(
            "diagnostic thresholds may only tighten the release gates: "
            f"max_rhat <= {RELEASE_MAX_RHAT}, "
            f"min_ess >= {RELEASE_MIN_ESS:.0f}, "
            f"max_divergences <= {RELEASE_MAX_DIVERGENCES}"
        )
    return thresholds


def enforce_diagnostics(
    rhat_max,
    ess_min,
    divergences,
    *,
    max_rhat=RELEASE_MAX_RHAT,
    min_ess=RELEASE_MIN_ESS,
    max_divergences=RELEASE_MAX_DIVERGENCES,
):
    thresholds = _validate_diagnostic_thresholds(
        max_rhat,
        min_ess,
        max_divergences,
    )
    max_rhat, min_ess, max_divergences = thresholds
    values = (float(rhat_max), float(ess_min), float(divergences))
    if not all(np.isfinite(value) for value in values):
        raise DiagnosticsError(
            "diagnostics contain non-finite values; no current output files were written"
        )
    failures = []
    if values[0] >= max_rhat:
        failures.append(f"max R-hat {values[0]:.4f} >= {max_rhat:.4f}")
    if values[1] <= min_ess:
        failures.append(f"min bulk-ESS {values[1]:.0f} <= {min_ess:.0f}")
    if int(values[2]) > max_divergences:
        failures.append(f"divergences {int(values[2])} > {max_divergences}")
    if failures:
        raise DiagnosticsError(
            "; ".join(failures) + "; no current output files were written"
        )


def _validate_sampling_controls(draws, tune, chains, cores, target_accept):
    controls = {
        "draws": draws,
        "tune": tune,
        "chains": chains,
        "cores": cores,
    }
    for name, value in controls.items():
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{name} must be an integer")
    if draws < 1 or tune < 0 or chains < 2:
        raise ValueError(
            "draws must be positive, tune nonnegative, and chains at least 2"
        )
    if cores < 1 or cores > chains:
        raise ValueError("cores must satisfy 1 <= cores <= chains")
    if not 0 < target_accept < 1:
        raise ValueError("target_accept must be strictly between 0 and 1")


def _validate_student_df(student_df):
    if (
        isinstance(student_df, bool)
        or not isinstance(student_df, (int, float, np.integer, np.floating))
        or not np.isfinite(float(student_df))
        or float(student_df) <= 2
    ):
        raise ValueError("student_df must be finite and greater than 2")


def _count_vector(name, values):
    try:
        counts = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a one-dimensional integer vector") from exc
    if counts.ndim != 1 or len(counts) < 1:
        raise ValueError(f"{name} must be a non-empty one-dimensional vector")
    if (
        not np.isfinite(counts).all()
        or np.any(counts != np.floor(counts))
        or np.any(counts > np.iinfo(np.int64).max)
    ):
        raise ValueError(f"{name} must contain finite integer-valued counts")
    return counts.astype(np.int64)


def fit_pymc(
    n0,
    c0,
    n1,
    c1,
    F,
    cost=COST,
    draws=1000,
    tune=1000,
    chains=4,
    cores=1,
    target_accept=0.9,
    seed=0,
    cand_F=None,
    student_df=4.0,
    nuts_sampler="pymc",
    max_rhat=RELEASE_MAX_RHAT,
    min_ess=RELEASE_MIN_ESS,
    max_divergences=RELEASE_MAX_DIVERGENCES,
    progressbar=True,
):
    _validate_sampling_controls(draws, tune, chains, cores, target_accept)
    _validate_student_df(student_df)
    _validate_diagnostic_thresholds(max_rhat, min_ess, max_divergences)
    n0, c0, n1, c1 = (
        _count_vector(name, values)
        for name, values in (("n0", n0), ("c0", c0), ("n1", n1), ("c1", c1))
    )
    F = np.asarray(F, dtype=float)
    if not np.isfinite(cost):
        raise ValueError("cost must be finite")
    if not (len(n0) == len(c0) == len(n1) == len(c1) == len(F)):
        raise ValueError("count and feature row counts must match")
    if F.ndim != 2 or F.shape[1] < 1 or not np.isfinite(F).all():
        raise ValueError("F must be a finite, non-empty two-dimensional matrix")
    if np.any(n0 < 0) or np.any(n1 < 0) or np.any(c0 < 0) or np.any(c1 < 0):
        raise ValueError("counts must be nonnegative")
    if np.any(c0 > n0) or np.any(c1 > n1):
        raise ValueError("conversions cannot exceed sessions")
    if cand_F is not None:
        cand_F = np.asarray(cand_F, dtype=float)
        if (
            cand_F.ndim != 2
            or cand_F.shape[1] != F.shape[1]
            or not np.isfinite(cand_F).all()
        ):
            raise ValueError("cand_F must be finite and have the same columns as F")

    import arviz as az
    import pymc as pm

    NQ, K = F.shape
    with pm.Model():
        gamma = pm.Normal("gamma", 0.0, 1.0, shape=K)
        beta = pm.Normal("beta", 0.0, 1.0, shape=K)
        sigma_a = pm.HalfNormal("sigma_a", 1.5)
        sigma_u = pm.HalfNormal("sigma_u", 0.3)
        a_raw = pm.Normal("a_raw", 0.0, 1.0, shape=NQ)
        u_raw = pm.StudentT("u_raw", nu=student_df, mu=0.0, sigma=1.0, shape=NQ)
        alpha = pm.Deterministic("alpha", pm.math.dot(F, gamma) + sigma_a * a_raw)
        b = pm.Deterministic("b", pm.math.dot(F, beta) + sigma_u * u_raw)
        pm.Binomial("y0", n=n0, p=pm.math.invlogit(alpha), observed=c0)
        pm.Binomial("y1", n=n1, p=pm.math.invlogit(alpha + b), observed=c1)
        try:
            idata = pm.sample(
                draws=draws,
                tune=tune,
                chains=chains,
                cores=cores,
                target_accept=target_accept,
                random_seed=seed,
                nuts_sampler=nuts_sampler,
                progressbar=progressbar,
            )
        except (EOFError, BrokenPipeError) as exc:
            if cores > 1:
                detail = "retry with --cores 1 for sequential chain sampling"
            else:
                detail = "worker startup failed even with sequential chain sampling"
            raise RuntimeError(f"PyMC sampling startup failed ({detail})") from exc

    # ---- diagnostics gate ----
    diagnostic_variables = ["gamma", "beta", "sigma_a", "sigma_u", "alpha", "b"]
    summ = az.summary(
        idata,
        var_names=diagnostic_variables,
        kind="diagnostics",
        round_to="none",
    )
    rhat_max = float(summ["r_hat"].max())
    ess_min = float(summ["ess_bulk"].min())
    worst_rhat = str(summ["r_hat"].idxmax())
    worst_ess = str(summ["ess_bulk"].idxmin())
    ndiv = int(idata.sample_stats["diverging"].values.sum())
    print(
        f"diagnostics: max R-hat {rhat_max:.4f} ({worst_rhat}) | "
        f"min bulk-ESS {ess_min:.0f} ({worst_ess}) | divergences {ndiv}"
    )
    enforce_diagnostics(
        rhat_max,
        ess_min,
        ndiv,
        max_rhat=max_rhat,
        min_ess=min_ess,
        max_divergences=max_divergences,
    )

    # ---- posterior of net tau on the probability scale ----
    post = idata.posterior
    A = post["alpha"].stack(s=("chain", "draw")).values.T  # S x NQ
    B = post["b"].stack(s=("chain", "draw")).values.T
    tau = expit(A + B) - expit(A) - cost
    out = dict(
        p_neg=(tau < 0).mean(0),
        tau_mean=tau.mean(0),
        tau_sd=tau.std(0),
        student_df=float(student_df),
        sigma_u=float(post["sigma_u"].mean()),
        rhat_max=rhat_max,
        ess_min=ess_min,
        divergences=ndiv,
    )

    # ---- posterior predictive for unseen candidates (expansion ranking) ----
    if cand_F is not None:
        rng = np.random.default_rng(seed)
        G = post["gamma"].stack(s=("chain", "draw")).values.T  # S x K
        Bt = post["beta"].stack(s=("chain", "draw")).values.T
        sa = post["sigma_a"].stack(s=("chain", "draw")).values
        su = post["sigma_u"].stack(s=("chain", "draw")).values
        S, NC = len(sa), len(cand_F)
        pos = np.zeros(NC)
        tot = np.zeros(NC)
        for s_i in range(S):  # stream to bound memory
            a_c = cand_F @ G[s_i] + sa[s_i] * rng.standard_normal(NC)
            b_c = cand_F @ Bt[s_i] + su[s_i] * rng.standard_t(student_df, NC)
            tc = expit(a_c + b_c) - expit(a_c) - cost
            pos += tc > 0
            tot += tc
        out |= dict(cand_p_pos=pos / S, cand_mean=tot / S)
    return out


def _safe_correlation(left, right):
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    if len(left) < 2 or np.std(left) <= 1e-15 or np.std(right) <= 1e-15:
        return None
    value = float(np.corrcoef(left, right)[0, 1])
    return value if np.isfinite(value) else None


def _truth_recovery_metrics(tau_mean, tau_sd, p_neg, truth):
    mean = np.asarray(tau_mean, dtype=float)
    sd = np.asarray(tau_sd, dtype=float)
    probability = np.asarray(p_neg, dtype=float)
    truth = np.asarray(truth, dtype=float)
    if not (len(mean) == len(sd) == len(probability) == len(truth)):
        raise ValueError("synthetic recovery arrays must have equal lengths")
    if (
        not all(np.isfinite(values).all() for values in (mean, sd, probability, truth))
        or np.any(sd < 0)
        or np.any((probability < 0) | (probability > 1))
    ):
        raise ValueError("synthetic recovery arrays contain invalid values")
    error = mean - truth
    is_negative = truth < 0
    normal_approx_half_width = 1.6448536269514722 * sd
    return {
        "row_count": int(len(truth)),
        "mean_error": float(np.mean(error)),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "tau_mean_truth_correlation": _safe_correlation(mean, truth),
        "negative_probability_brier": float(
            np.mean((probability - is_negative.astype(float)) ** 2)
        ),
        "posterior_mean_sign_accuracy": float(np.mean((mean < 0) == is_negative)),
        "normal_approx_90pct_interval_coverage": float(
            np.mean(
                (truth >= mean - normal_approx_half_width)
                & (truth <= mean + normal_approx_half_width)
            )
        ),
    }


def synthetic_recovery_summary(posterior, world, *, top_k=300):
    """Return descriptive recovery metrics against known synthetic truth.

    The returned values are not acceptance gates and are not production
    evidence. They make model recovery and benchmark behavior inspectable.
    """

    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    truth = np.asarray(world["net_allowlist"], dtype=float)
    pymc_metrics = _truth_recovery_metrics(
        posterior["tau_mean"],
        posterior["tau_sd"],
        posterior["p_neg"],
        truth,
    )
    gaussian = fit_gaussian_eb(
        world["n0"],
        world["c0"],
        world["n1"],
        world["c1"],
        world["F"],
    )
    robust_negative = fit_robust_irls_negative_benchmark(
        world["n0"],
        world["c0"],
        world["n1"],
        world["c1"],
        world["F"],
    )
    outlier_mask = np.asarray(world["outlier_allowlist"], dtype=bool)
    outlier_metrics = None
    if np.any(outlier_mask):
        outlier_metrics = _truth_recovery_metrics(
            np.asarray(posterior["tau_mean"])[outlier_mask],
            np.asarray(posterior["tau_sd"])[outlier_mask],
            np.asarray(posterior["p_neg"])[outlier_mask],
            truth[outlier_mask],
        )

    candidate_mean = np.asarray(posterior["cand_mean"], dtype=float)
    candidate_truth = np.asarray(world["net_candidates"], dtype=float)
    if (
        len(candidate_mean) != len(candidate_truth)
        or not np.isfinite(candidate_mean).all()
        or not np.isfinite(candidate_truth).all()
    ):
        raise ValueError("synthetic candidate predictions do not match truth")
    selected_count = min(int(top_k), len(candidate_truth))
    selected = np.argsort(-candidate_mean)[:selected_count]
    candidate_rank_correlation = _safe_correlation(
        rankdata(candidate_mean),
        rankdata(candidate_truth),
    )

    return {
        "scope": "synthetic_only_not_production_evidence",
        "automatic_gates": "sampler_diagnostics_only",
        "diagnostics": {
            "max_rhat": float(posterior["rhat_max"]),
            "min_bulk_ess": float(posterior["ess_min"]),
            "divergences": int(posterior["divergences"]),
            "student_df_prespecified": float(posterior["student_df"]),
        },
        "allowlist_truth_recovery": {
            "pymc": pymc_metrics,
            "gaussian_eb_orientation_only": _truth_recovery_metrics(
                gaussian["tau_mean"],
                gaussian["tau_sd"],
                gaussian["p_neg"],
                truth,
            ),
            "robust_irls_recorded_negative_benchmark": _truth_recovery_metrics(
                robust_negative["tau_mean"],
                robust_negative["tau_sd"],
                robust_negative["p_neg"],
                truth,
            ),
            "pymc_outlier_subset": outlier_metrics,
        },
        "candidate_truth_ranking": {
            "reported_top_k": selected_count,
            "rank_correlation_spearman": candidate_rank_correlation,
            "top_k_share_net_positive": float(np.mean(candidate_truth[selected] > 0)),
            "all_candidate_share_net_positive": float(np.mean(candidate_truth > 0)),
            "top_k_mean_net_effect": float(np.mean(candidate_truth[selected])),
            "all_candidate_mean_net_effect": float(np.mean(candidate_truth)),
        },
    }


def demo(
    outlier_share,
    seed,
    *,
    draws=1000,
    tune=1000,
    chains=4,
    cores=1,
    target_accept=0.9,
    student_df=4.0,
    nuts_sampler="pymc",
    max_rhat=RELEASE_MAX_RHAT,
    min_ess=RELEASE_MIN_ESS,
    max_divergences=RELEASE_MAX_DIVERGENCES,
    top_k=300,
    progressbar=True,
):
    _validate_sampling_controls(draws, tune, chains, cores, target_accept)
    _validate_student_df(student_df)
    _validate_diagnostic_thresholds(max_rhat, min_ess, max_divergences)
    world = make_synthetic_world(outlier_share=outlier_share, seed=seed)
    print("PyMC synthetic fit ...")
    posterior = fit_pymc(
        world["n0"],
        world["c0"],
        world["n1"],
        world["c1"],
        world["F"],
        cand_F=world["FC"],
        seed=seed,
        draws=draws,
        tune=tune,
        chains=chains,
        cores=cores,
        target_accept=target_accept,
        student_df=student_df,
        nuts_sampler=nuts_sampler,
        max_rhat=max_rhat,
        min_ess=min_ess,
        max_divergences=max_divergences,
        progressbar=progressbar,
    )
    summary = synthetic_recovery_summary(posterior, world, top_k=top_k)
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return summary


def production(
    path,
    cost,
    *,
    output="posteriors_pymc.csv",
    candidates=None,
    candidate_output="candidate_posteriors_pymc.csv",
    quadratic=False,
    max_basis_terms=DEFAULT_MAX_BASIS_TERMS,
    draws=1000,
    tune=1000,
    chains=4,
    cores=1,
    target_accept=0.9,
    seed=0,
    student_df=4.0,
    nuts_sampler="pymc",
    max_rhat=RELEASE_MAX_RHAT,
    min_ess=RELEASE_MIN_ESS,
    max_divergences=RELEASE_MAX_DIVERGENCES,
    progressbar=True,
    fit_fn=fit_pymc,
):
    output_paths = [output]
    if candidates is not None:
        output_paths.append(candidate_output)
    archived = archive_existing_outputs(
        *output_paths, protected_paths=(path, candidates)
    )
    if archived:
        print(
            "archived prior output(s) before this run: "
            + ", ".join(str(stale) for _, stale in archived)
        )
    _validate_sampling_controls(draws, tune, chains, cores, target_accept)
    _validate_student_df(student_df)
    _validate_diagnostic_thresholds(max_rhat, min_ess, max_divergences)
    data = load_allowlist_csv(path)
    design = FeatureDesign.fit(
        data.features, quadratic=quadratic, max_terms=max_basis_terms
    )
    F = design.transform(data.features)
    candidate_data = None
    candidate_F = None
    if candidates is not None:
        candidate_data = load_candidate_csv(candidates, data.feature_names)
        overlap = set(data.ids).intersection(candidate_data.ids)
        if overlap:
            raise DataValidationError(
                f"candidate query_id values must be off-allowlist; overlap includes {next(iter(overlap))!r}"
            )
        candidate_F = design.transform(candidate_data.features)
    res = fit_fn(
        data.n0,
        data.c0,
        data.n1,
        data.c1,
        F,
        cost=cost,
        draws=draws,
        tune=tune,
        chains=chains,
        cores=cores,
        target_accept=target_accept,
        seed=seed,
        cand_F=candidate_F,
        student_df=student_df,
        nuts_sampler=nuts_sampler,
        max_rhat=max_rhat,
        min_ess=min_ess,
        max_divergences=max_divergences,
        progressbar=progressbar,
    )
    enforce_diagnostics(
        res.get("rhat_max", np.nan),
        res.get("ess_min", np.nan),
        res.get("divergences", np.nan),
        max_rhat=max_rhat,
        min_ess=min_ess,
        max_divergences=max_divergences,
    )
    posterior_output_rows = list(
        posterior_rows(data.ids, res["tau_mean"], res["tau_sd"], res["p_neg"])
    )
    candidate_output_rows = None
    candidate_fields = (
        "query_id",
        "rank_within_near_support",
        "tau_mean_predictive",
        "p_net_positive_predictive",
        "support_distance_nearest_standardized",
        "support_threshold_training_nn_p95",
        "support_flag_heuristic",
    )
    if candidate_data is not None:
        train_z = design.standardized(data.features)
        candidate_z = design.standardized(candidate_data.features)
        distances, threshold, in_support = support_distances(train_z, candidate_z)
        candidate_output_rows = list(
            candidate_rows(
                candidate_data.ids,
                res["cand_mean"],
                res["cand_p_pos"],
                distances,
                threshold,
                in_support,
            )
        )
    if candidate_output_rows is not None:
        write_csv_atomic(
            candidate_output,
            candidate_fields,
            candidate_output_rows,
        )
    # Write the primary posterior report last. Its presence then indicates that
    # all requested companion output writes for this invocation succeeded.
    write_csv_atomic(
        output,
        (
            "query_id",
            "tau_mean",
            "tau_sd",
            "p_neg",
            "diagnostic_p_neg_band",
        ),
        posterior_output_rows,
    )
    print(
        f"wrote {output} after diagnostics passed "
        f"(prespecified student_df={res['student_df']:.1f}, "
        f"sigma_u={res['sigma_u']:.4f})"
    )
    return {"posterior": res, "design": design}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--outliers", type=float, default=0.03)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--data")
    ap.add_argument("--cost", type=float, default=COST)
    ap.add_argument(
        "--output",
        default="posteriors_pymc.csv",
        help="posterior report; diagnostic probability bands are not policy actions",
    )
    ap.add_argument("--candidates")
    ap.add_argument("--candidate-output", default="candidate_posteriors_pymc.csv")
    ap.add_argument(
        "--quadratic",
        action="store_true",
        help="explicit opt-in to a guarded quadratic+interaction basis",
    )
    ap.add_argument(
        "--linear",
        action="store_true",
        help="deprecated compatibility flag; standardized linear is now the default",
    )
    ap.add_argument("--max-basis-terms", type=int, default=DEFAULT_MAX_BASIS_TERMS)
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--tune", type=int, default=1000)
    ap.add_argument("--chains", type=int, default=4)
    ap.add_argument(
        "--cores",
        type=int,
        default=1,
        help="parallel sampling workers; must satisfy 1 <= cores <= chains",
    )
    ap.add_argument("--target-accept", type=float, default=0.9)
    ap.add_argument(
        "--student-df",
        type=float,
        default=4.0,
        help="prespecified Student-t degrees of freedom (>2); use for sensitivity runs",
    )
    ap.add_argument("--nuts-sampler", default="pymc")
    ap.add_argument(
        "--max-rhat",
        type=float,
        default=RELEASE_MAX_RHAT,
        help="R-hat gate; may be stricter than 1.01 but not weaker",
    )
    ap.add_argument(
        "--min-ess",
        type=float,
        default=RELEASE_MIN_ESS,
        help="bulk-ESS gate; may be stricter than 400 but not weaker",
    )
    ap.add_argument(
        "--max-divergences",
        type=int,
        default=RELEASE_MAX_DIVERGENCES,
        help="divergence gate; release maximum is fixed at zero",
    )
    ap.add_argument(
        "--demo-top-k",
        type=int,
        default=300,
        help="candidate slice reported against truth in --demo; not an acceptance gate",
    )
    ap.add_argument("--no-progress", action="store_true")
    a = ap.parse_args()
    if a.linear and a.quadratic:
        ap.error("--linear and --quadratic cannot be used together")
    try:
        if a.demo:
            demo(
                a.outliers,
                a.seed,
                draws=a.draws,
                tune=a.tune,
                chains=a.chains,
                cores=a.cores,
                target_accept=a.target_accept,
                student_df=a.student_df,
                nuts_sampler=a.nuts_sampler,
                max_rhat=a.max_rhat,
                min_ess=a.min_ess,
                max_divergences=a.max_divergences,
                top_k=a.demo_top_k,
                progressbar=not a.no_progress,
            )
        elif a.data:
            production(
                a.data,
                a.cost,
                output=a.output,
                candidates=a.candidates,
                candidate_output=a.candidate_output,
                quadratic=a.quadratic,
                max_basis_terms=a.max_basis_terms,
                draws=a.draws,
                tune=a.tune,
                chains=a.chains,
                cores=a.cores,
                target_accept=a.target_accept,
                seed=a.seed,
                student_df=a.student_df,
                nuts_sampler=a.nuts_sampler,
                max_rhat=a.max_rhat,
                min_ess=a.min_ess,
                max_divergences=a.max_divergences,
                progressbar=not a.no_progress,
            )
        else:
            print(__doc__)
    except (DataValidationError, DiagnosticsError, RuntimeError, ValueError) as exc:
        ap.exit(2, f"error: {exc}\n")
