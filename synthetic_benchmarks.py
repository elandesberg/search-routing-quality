"""Synthetic fixtures and non-production orientation benchmarks.

Nothing in this module is a production estimator or policy rule. The Gaussian
empirical-Bayes approximation is retained as a cheap orientation benchmark.
The robust-IRLS variant is retained only to make a recorded negative experiment
inspectable; it performed worse in the original outlier simulation and is not a
recommended middle rung between Gaussian EB and the PyMC model.
"""

from __future__ import annotations

import numpy as np
from scipy.special import expit
from scipy.stats import norm


COST = 0.002


def synthetic_basis(features: np.ndarray) -> np.ndarray:
    """Return the fixed quadratic basis used only by the synthetic benchmark."""

    x = np.asarray(features, dtype=float)
    if x.ndim != 2 or x.shape[1] < 1 or not np.isfinite(x).all():
        raise ValueError("features must be a finite, non-empty two-dimensional matrix")
    columns = [np.ones((len(x), 1)), x, x**2]
    columns.extend(
        (x[:, i] * x[:, j])[:, None]
        for i in range(x.shape[1])
        for j in range(i + 1, x.shape[1])
    )
    return np.hstack(columns)


def _observed_effects(
    n0: np.ndarray,
    c0: np.ndarray,
    n1: np.ndarray,
    c1: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    n0, c0, n1, c1 = (
        np.asarray(values, dtype=float) for values in (n0, c0, n1, c1)
    )
    if not (n0.ndim == c0.ndim == n1.ndim == c1.ndim == 1):
        raise ValueError("benchmark count inputs must be one-dimensional")
    if not (len(n0) == len(c0) == len(n1) == len(c1)):
        raise ValueError("benchmark count inputs must have equal lengths")
    if (
        not all(np.isfinite(values).all() for values in (n0, c0, n1, c1))
        or np.any(n0 < 0)
        or np.any(n1 < 0)
        or np.any(c0 < 0)
        or np.any(c1 < 0)
        or np.any(c0 > n0)
        or np.any(c1 > n1)
    ):
        raise ValueError("benchmark counts must satisfy 0 <= conversions <= sessions")

    observed = (c1 / np.maximum(n1, 1)) - (c0 / np.maximum(n0, 1))
    pooled = (c0 + c1 + 1) / (n0 + n1 + 2)
    variance = pooled * (1 - pooled) * (
        1 / np.maximum(n0, 1) + 1 / np.maximum(n1, 1)
    )
    variance[(n0 < 1) | (n1 < 1)] = np.inf
    return observed, variance


def _validated_features(features: np.ndarray, row_count: int) -> np.ndarray:
    design = np.asarray(features, dtype=float)
    if (
        design.ndim != 2
        or len(design) != row_count
        or design.shape[1] < 1
        or not np.isfinite(design).all()
    ):
        raise ValueError("benchmark features must be finite and match count rows")
    return design


def _updated_prior_variance(
    residual_sq: np.ndarray,
    variance: np.ndarray,
    weights: np.ndarray,
    current: float,
) -> float:
    good = np.isfinite(variance) & (variance < 0.02**2)
    if not np.any(good):
        return current
    usable_weights = np.asarray(weights)[good]
    if not np.isfinite(usable_weights).all() or float(usable_weights.sum()) <= 0:
        return current
    estimate = float(
        np.average(
            np.asarray(residual_sq)[good] - variance[good],
            weights=usable_weights,
        )
    )
    return max(estimate, 1e-7) if np.isfinite(estimate) else current


def fit_gaussian_eb(
    n0: np.ndarray,
    c0: np.ndarray,
    n1: np.ndarray,
    c1: np.ndarray,
    features: np.ndarray,
    *,
    cost: float = COST,
) -> dict[str, np.ndarray]:
    """Fit the Gaussian two-stage EB orientation benchmark."""

    if not np.isfinite(cost):
        raise ValueError("cost must be finite")
    observed, variance = _observed_effects(n0, c0, n1, c1)
    design = _validated_features(features, len(observed))
    prior_variance = 0.004**2
    beta = np.zeros(design.shape[1])
    fitted = np.zeros(len(design))
    for _ in range(2):
        weights = 1 / (variance + prior_variance)
        gram = (
            (design * weights[:, None]).T @ design
            + 50.0 * np.eye(design.shape[1])
        )
        beta = np.linalg.solve(gram, (design * weights[:, None]).T @ observed)
        fitted = design @ beta
        prior_variance = _updated_prior_variance(
            (observed - fitted) ** 2,
            variance,
            1 / variance,
            prior_variance,
        )
    precision = 1 / variance + 1 / prior_variance
    posterior = (observed / variance + fitted / prior_variance) / precision
    posterior[~np.isfinite(variance)] = fitted[~np.isfinite(variance)]
    posterior_sd = np.sqrt(
        1 / np.where(np.isfinite(variance), precision, 1 / prior_variance)
    )
    net_mean = posterior - cost
    return {
        "p_neg": norm.cdf(-net_mean / posterior_sd),
        "tau_mean": net_mean,
        "tau_sd": posterior_sd,
        "beta": beta,
    }


def fit_robust_irls_negative_benchmark(
    n0: np.ndarray,
    c0: np.ndarray,
    n1: np.ndarray,
    c1: np.ndarray,
    features: np.ndarray,
    *,
    cost: float = COST,
    nu: float = 4.0,
    iterations: int = 6,
) -> dict[str, np.ndarray]:
    """Fit the recorded-negative robust-IRLS approximation.

    This approximation downweights standardized residuals and can confound a
    genuinely deviant query with a noisily measured one. It is retained only as
    a reproducible negative benchmark and must not be used for production.
    """

    if not np.isfinite(cost):
        raise ValueError("cost must be finite")
    if not np.isfinite(nu) or nu <= 0 or iterations < 1:
        raise ValueError("nu must be positive and iterations must be at least 1")
    observed, variance = _observed_effects(n0, c0, n1, c1)
    design = _validated_features(features, len(observed))
    prior_variance = 0.004**2
    robust_weights = np.ones(len(observed))
    beta = np.zeros(design.shape[1])
    fitted = np.zeros(len(design))
    for _ in range(iterations):
        weights = robust_weights / (variance + prior_variance)
        gram = (
            (design * weights[:, None]).T @ design
            + 50.0 * np.eye(design.shape[1])
        )
        beta = np.linalg.solve(gram, (design * weights[:, None]).T @ observed)
        fitted = design @ beta
        standardized_sq = (observed - fitted) ** 2 / (
            variance + prior_variance
        )
        robust_weights = np.where(
            np.isfinite(variance),
            (nu + 1) / (nu + standardized_sq),
            1.0,
        )
        prior_variance = _updated_prior_variance(
            (observed - fitted) ** 2,
            variance,
            robust_weights / variance,
            prior_variance,
        )
    effective_prior_variance = prior_variance / np.clip(
        robust_weights, 0.05, None
    )
    precision = 1 / variance + 1 / effective_prior_variance
    posterior = (
        observed / variance + fitted / effective_prior_variance
    ) / precision
    posterior[~np.isfinite(variance)] = fitted[~np.isfinite(variance)]
    posterior_sd = np.sqrt(
        1 / np.where(np.isfinite(variance), precision, 1 / prior_variance)
    )
    net_mean = posterior - cost
    return {
        "p_neg": norm.cdf(-net_mean / posterior_sd),
        "tau_mean": net_mean,
        "tau_sd": posterior_sd,
        "beta": beta,
    }


def make_synthetic_world(
    outlier_share: float = 0.03,
    seed: int = 0,
) -> dict[str, np.ndarray]:
    """Create the fixed synthetic allowlist world and its known ground truth."""

    if not np.isfinite(outlier_share) or not 0 <= outlier_share <= 1:
        raise ValueError("outlier_share must be between 0 and 1")
    rng = np.random.default_rng(seed)
    query_count, allowlist_size, dimension = 22_000, 2_000, 6
    features = rng.standard_normal((query_count, dimension))
    signal = (
        0.012
        * np.tanh(
            0.9
            * (
                features[:, 0]
                + 0.8 * features[:, 1] * features[:, 2]
                - 0.5 * features[:, 3] ** 2
            )
            + 0.3
        )
        + 0.003
    )
    gross_effect = signal + rng.normal(0, 0.006, query_count)
    outlier_mask = rng.random(query_count) < outlier_share
    gross_effect = np.where(outlier_mask, gross_effect - 0.025, gross_effect)
    net_effect = gross_effect - COST
    baseline = expit(
        -3.1 + 0.5 * features[:, 5] + 0.25 * features[:, 0]
    )
    heuristic = signal + rng.normal(0, 0.02, query_count)
    order = np.argsort(-heuristic)
    allowlist = order[:allowlist_size]
    candidates = order[allowlist_size:]
    traffic_weights = (np.arange(allowlist_size) + 1.0) ** -1.05
    traffic_weights /= traffic_weights.sum()
    total_sessions = np.round(traffic_weights * 150_000 * 8).astype(int)
    n1 = rng.binomial(total_sessions, 0.5)
    n0 = total_sessions - n1
    treatment = np.clip(
        baseline[allowlist] + gross_effect[allowlist],
        1e-4,
        0.6,
    )
    c1 = rng.binomial(n1, treatment)
    c0 = rng.binomial(n0, baseline[allowlist])
    candidate_subset = candidates[:20_000]
    return {
        "n0": n0,
        "c0": c0,
        "n1": n1,
        "c1": c1,
        "F": synthetic_basis(features[allowlist]),
        "FC": synthetic_basis(features[candidate_subset]),
        "net_allowlist": net_effect[allowlist],
        "net_candidates": net_effect[candidate_subset],
        "outlier_allowlist": outlier_mask[allowlist],
        "traffic_weights": traffic_weights,
        "total_sessions": total_sessions,
    }
