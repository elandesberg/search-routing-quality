"""Starter interfaces for the query-level Bayes work package.

This file defines contracts only. It deliberately contains no estimator,
production connector, filesystem writer, or policy rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Protocol, Sequence


EstimatorName = Literal["empirical_bayes", "full_bayes"]
IntervalType = Literal["plug_in_eb_interval", "posterior_credible_interval"]
CostMode = Literal["per_query", "constant", "not_configured"]
DecisionStatus = Literal["not_scored", "scored_proposal"]
PrerequisiteStatus = Literal["PASS", "BLOCKED"]
EstimatorStatus = Literal["PASS", "BLOCKED"]
StageState = Literal["PASS", "BLOCKED"]
SupportStatus = Literal[
    "in_randomized_support",
    "sensitivity_only",
    "outside_support",
]


@dataclass(frozen=True)
class QueryCount:
    """Validated first-shadow-trigger-positive aggregate for one query ID."""

    query_id: str
    n_control: int
    y_control: int
    n_treatment: int
    y_treatment: int
    token_count: int
    traffic_weight: float
    cost_outcome_units: float | None


@dataclass(frozen=True)
class PrerequisiteCheck:
    """One evidence-backed causal-analysis prerequisite."""

    status: PrerequisiteStatus
    evidence_id: str
    note: str


@dataclass(frozen=True)
class StageStatus:
    """Redacted, machine-readable state for one pipeline stage."""

    state: StageState
    stage: str
    reason_codes: tuple[str, ...]
    diagnostics: Mapping[str, object]


@dataclass(frozen=True)
class DiagnosticLimits:
    """Release limits that an implementation may tighten but never weaken."""

    max_rhat_exclusive: float = 1.01
    min_bulk_ess_exclusive: int = 400
    min_tail_ess_exclusive: int = 400
    max_divergences: int = 0


@dataclass(frozen=True)
class EstimatorConfig:
    """Estimator settings after config validation and placeholder rejection."""

    name: EstimatorName
    seed: int
    settings: Mapping[str, object]
    validation_settings: Mapping[str, object]
    diagnostic_limits: DiagnosticLimits


@dataclass(frozen=True)
class FeatureTransform:
    """One recorded transform shared by EB, full Bayes, and sensitivities."""

    log1p_mean: float
    log1p_sample_sd: float
    minimum_token_count: int
    maximum_token_count: int
    tokenizer_version: str
    canonicalization_version: str


@dataclass(frozen=True)
class ValidationResult:
    """Validated records/counts plus a redacted audit."""

    status: StageStatus
    query_counts: tuple[QueryCount, ...]
    audit: Mapping[str, object]


@dataclass(frozen=True)
class CountBuildResult:
    """Canonical counts and their one shared query-length transform."""

    status: StageStatus
    query_counts: tuple[QueryCount, ...]
    feature_transform: FeatureTransform
    audit: Mapping[str, object]


@dataclass(frozen=True)
class PosteriorRow:
    """Shared probability-scale summary for one query and estimator."""

    run_id: str
    query_id: str
    estimator: EstimatorName
    interval_kind: IntervalType
    token_count: int
    query_length_log1p: float
    query_length_z: float
    n_control: int
    y_control: int
    n_treatment: int
    y_treatment: int
    raw_rate_control: float
    raw_rate_treatment: float
    raw_delta: float
    p_control_mean: float
    p_control_median: float
    p_treatment_mean: float
    p_treatment_median: float
    delta_mean: float
    delta_quantiles: Mapping[str, float]
    p_delta_gt_0: float
    tau_mean: float | None
    tau_quantiles: Mapping[str, float] | None
    p_tau_gt_0: float | None
    cost_mode: CostMode
    cost_outcome_units: float | None
    traffic_weight: float
    expected_traffic_weighted_net_value: float | None
    expected_regret_if_scored: float | None
    prior_mean_control: float | None
    prior_mean_treatment: float | None
    prior_concentration_control: float | None
    prior_concentration_treatment: float | None
    shrinkage_weight_control: float | None
    shrinkage_weight_treatment: float | None
    posterior_sd_delta: float
    mcse_delta_mean: float | None
    mcse_p_delta_gt_0: float | None
    support_status: SupportStatus
    overlap_status: str
    convergence_status: str
    predictive_status: str
    diagnostic_status: str
    decision_status: DecisionStatus
    model_spec_version: str
    shadow_policy_version: str
    canonicalization_version: str
    tokenizer_version: str
    outcome_definition_version: str
    analysis_window_id: str


@dataclass(frozen=True)
class EstimatorResult:
    """Structured fit result retaining diagnostics and posterior-draw access."""

    estimator: EstimatorName
    status: EstimatorStatus
    summaries: tuple[PosteriorRow, ...]
    diagnostics: Mapping[str, object]
    posterior_draws_handle: Path | None
    config_fingerprint: str


@dataclass(frozen=True)
class ComparisonResult:
    """Aligned cross-estimator result with diagnostics and review flags."""

    status: EstimatorStatus
    aligned_rows: tuple[Mapping[str, object], ...]
    diagnostics: Mapping[str, object]


@dataclass(frozen=True)
class PolicyProposal:
    """Restricted next-cycle proposal; never an applied routing action."""

    status: StageStatus
    rows: tuple[Mapping[str, object], ...]
    decision_config_fingerprint: str


class QueryEffectEstimator(Protocol):
    """Common estimator boundary for EB and full Bayes."""

    def fit(
        self,
        rows: Sequence[QueryCount],
        feature_transform: FeatureTransform,
        config: EstimatorConfig,
    ) -> EstimatorResult:
        """Fit without applying actions and retain diagnostics/draw access."""


def load_query_counts(path: Path) -> tuple[QueryCount, ...]:
    """Load and validate the exact query-count CSV contract."""

    raise NotImplementedError("implementation task")


def load_prerequisite_audit(path: Path) -> Mapping[str, PrerequisiteCheck]:
    """Load the audit and fail if any required check is not PASS."""

    raise NotImplementedError("implementation task")


def validate_prerequisites(
    checks: Mapping[str, PrerequisiteCheck],
) -> None:
    """Fail closed unless every required prerequisite is explicitly PASS."""

    raise NotImplementedError("implementation task")


def audit_prerequisites(
    manifest: Mapping[str, object],
    run_configuration: Mapping[str, object],
) -> StageStatus:
    """Return PASS only when all required evidence-backed checks pass."""

    raise NotImplementedError("implementation task")


def validate_events(
    events: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
    run_configuration: Mapping[str, object],
) -> ValidationResult:
    """Validate event records without selecting on delivery or outcome."""

    raise NotImplementedError("implementation task")


def build_query_counts(
    events: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
    run_configuration: Mapping[str, object],
) -> CountBuildResult:
    """Build unweighted two-arm counts under the approved cohort rule."""

    raise NotImplementedError("implementation task")


def validate_query_counts(
    rows: Sequence[QueryCount],
    manifest: Mapping[str, object],
    aggregation_audit: Mapping[str, object] | None,
) -> ValidationResult:
    """Validate canonical aggregate counts and their secure source audit."""

    raise NotImplementedError("implementation task")


def fit_empirical_bayes(
    rows: Sequence[QueryCount],
    feature_transform: FeatureTransform,
    config: EstimatorConfig,
) -> EstimatorResult:
    """Fit beta-binomial regression and return labeled plug-in EB summaries."""

    raise NotImplementedError("implementation task")


def fit_full_bayes(
    rows: Sequence[QueryCount],
    feature_transform: FeatureTransform,
    config: EstimatorConfig,
) -> EstimatorResult:
    """Fit the correlated hierarchy and return posterior credible summaries."""

    raise NotImplementedError("implementation task")


def fit_query_length_transform(
    rows: Sequence[QueryCount],
) -> FeatureTransform:
    """Fit and return the recorded standardized log1p length transform."""

    raise NotImplementedError("implementation task")


def compare_estimators(
    empirical_bayes: EstimatorResult,
    full_bayes: EstimatorResult,
    run_configuration: Mapping[str, object],
) -> ComparisonResult:
    """Compare interval widths and probability-scale disagreements."""

    raise NotImplementedError("implementation task")


def summarize_query_draws(
    estimator_result: EstimatorResult,
    rows: Sequence[QueryCount],
    run_configuration: Mapping[str, object],
) -> tuple[PosteriorRow, ...]:
    """Build the shared summary without discarding posterior-draw access."""

    raise NotImplementedError("implementation task")


def score_static_policy(
    posterior_rows: Sequence[PosteriorRow],
    traffic: Mapping[str, float],
    run_configuration: Mapping[str, object],
) -> PolicyProposal:
    """Score a proposal only after an explicit decision configuration passes."""

    raise NotImplementedError("implementation task")
