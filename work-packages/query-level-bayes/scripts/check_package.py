#!/usr/bin/env python3
"""Validate the lightweight query-level Bayes scaffold using only the stdlib."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPAQUE_ID = re.compile(r"q_[0-9]{4}\Z")
TOLERANCE = Decimal("1e-12")

REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "AGENT_BRIEF.md",
    "TASK_CHECKLIST.md",
    "METHOD_CONTRACT.md",
    "DATA_CONTRACT.md",
    "INTERFACES.md",
    "ACCEPTANCE_CRITERIA.md",
    "DECISIONS_REQUIRED.md",
    "REFERENCES.md",
    "config/synthetic.example.json",
    "config/production.template.json",
    "schemas/query-counts.schema.json",
    "schemas/query-posteriors.schema.json",
    "schemas/eb-bootstrap-sensitivity.schema.json",
    "schemas/prerequisite-audit.schema.json",
    "fixtures/README.md",
    "fixtures/synthetic-query-counts.csv",
    "fixtures/synthetic-known-truth.csv",
    "fixtures/prerequisite-audit.pass.json",
    "fixtures/analysis-manifest.synthetic.json",
    "fixtures/aggregation-audit.synthetic.json",
    "starter/interfaces.py",
    "scripts/check_package.py",
)

TRUTH_HEADER = (
    "query_id",
    "p_control_true",
    "p_treatment_true",
    "delta_gross_true",
    "cost_outcome_units",
    "tau_net_true",
    "traffic_weight",
)

EXPECTED_POSTERIOR_HEADER = (
    "run_id",
    "query_id",
    "estimator",
    "interval_kind",
    "token_count",
    "query_length_log1p",
    "query_length_z",
    "n_control",
    "y_control",
    "n_treatment",
    "y_treatment",
    "raw_rate_control",
    "raw_rate_treatment",
    "raw_delta",
    "p_control_mean",
    "p_control_median",
    "p_treatment_mean",
    "p_treatment_median",
    "delta_mean",
    "delta_q025",
    "delta_q10",
    "delta_q25",
    "delta_q50",
    "delta_q75",
    "delta_q90",
    "delta_q975",
    "p_delta_gt_0",
    "tau_mean",
    "tau_q025",
    "tau_q10",
    "tau_q25",
    "tau_q50",
    "tau_q75",
    "tau_q90",
    "tau_q975",
    "p_tau_gt_0",
    "cost_mode",
    "cost_outcome_units",
    "traffic_weight",
    "expected_traffic_weighted_net_value",
    "expected_regret_if_scored",
    "prior_mean_control",
    "prior_mean_treatment",
    "prior_concentration_control",
    "prior_concentration_treatment",
    "shrinkage_weight_control",
    "shrinkage_weight_treatment",
    "posterior_sd_delta",
    "mcse_delta_mean",
    "mcse_p_delta_gt_0",
    "support_status",
    "overlap_status",
    "convergence_status",
    "predictive_status",
    "diagnostic_status",
    "decision_status",
    "model_spec_version",
    "shadow_policy_version",
    "canonicalization_version",
    "tokenizer_version",
    "outcome_definition_version",
    "analysis_window_id",
)


class CheckError(RuntimeError):
    """Raised when a scaffold invariant fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def load_json(relative_path: str) -> object:
    path = ROOT / relative_path
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise CheckError(f"{relative_path}: invalid JSON: {exc}") from exc


def decimal_value(raw: str, *, location: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise CheckError(f"{location}: expected a decimal number") from exc
    require(value.is_finite(), f"{location}: value must be finite")
    return value


def integer_value(raw: str, *, location: str) -> int:
    require(re.fullmatch(r"0|[1-9][0-9]*", raw) is not None, f"{location}: expected a nonnegative integer")
    return int(raw)


def read_csv(relative_path: str, expected_header: tuple[str, ...]) -> list[dict[str, str]]:
    path = ROOT / relative_path
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(
            tuple(reader.fieldnames or ()) == expected_header,
            f"{relative_path}: exact header mismatch",
        )
        rows = list(reader)
    require(rows, f"{relative_path}: expected at least one data row")
    require(
        all(None not in row for row in rows),
        f"{relative_path}: a row has more fields than the header",
    )
    return rows


def validate_required_files() -> None:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    require(not missing, f"missing required scaffold files: {missing}")


def validate_schemas() -> tuple[str, ...]:
    count_schema = load_json("schemas/query-counts.schema.json")
    posterior_schema = load_json("schemas/query-posteriors.schema.json")
    eb_sensitivity_schema = load_json("schemas/eb-bootstrap-sensitivity.schema.json")
    audit_schema = load_json("schemas/prerequisite-audit.schema.json")
    for name, schema in (
        ("query-counts", count_schema),
        ("query-posteriors", posterior_schema),
        ("eb-bootstrap-sensitivity", eb_sensitivity_schema),
        ("prerequisite-audit", audit_schema),
    ):
        require(isinstance(schema, dict), f"{name} schema must be a JSON object")
        require(
            schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
            f"{name} schema must declare JSON Schema draft 2020-12",
        )

    count_header = tuple(count_schema.get("x-csv-header", ()))
    require(
        count_header
        == (
            "query_id",
            "n_control",
            "y_control",
            "n_treatment",
            "y_treatment",
            "token_count",
            "traffic_weight",
            "cost_outcome_units",
        ),
        "query-counts schema has an unexpected CSV header",
    )
    require(
        tuple(posterior_schema.get("x-csv-header", ())) == EXPECTED_POSTERIOR_HEADER,
        "query-posteriors schema has an unexpected CSV header",
    )
    require(
        eb_sensitivity_schema.get("properties", {})
        .get("interval_kind", {})
        .get("const")
        == "eb_hyperparameter_sensitivity_interval",
        "EB bootstrap schema has the wrong interval kind",
    )
    required_checks = (
        audit_schema.get("properties", {})
        .get("checks", {})
        .get("required", [])
    )
    require(
        isinstance(required_checks, list) and len(required_checks) == 17,
        "prerequisite-audit schema must declare exactly seventeen required checks",
    )
    require(
        len(set(required_checks)) == len(required_checks),
        "prerequisite-audit schema contains duplicate required checks",
    )
    return tuple(required_checks)


def validate_counts(header: tuple[str, ...]) -> tuple[list[dict[str, str]], dict[str, dict[str, Decimal]]]:
    rows = read_csv("fixtures/synthetic-query-counts.csv", header)
    expected_ids = [f"q_{index:04d}" for index in range(1, 13)]
    ids = [row["query_id"] for row in rows]
    require(ids == expected_ids, "synthetic counts must use q_0001 through q_0012 in order")
    require(len(set(ids)) == len(ids), "synthetic counts contain duplicate query IDs")

    numeric_by_id: dict[str, dict[str, Decimal]] = {}
    total_weight = Decimal("0")
    has_zero_success_cell = False
    has_all_success_cell = False
    has_single_observation_cell = False
    for line_number, row in enumerate(rows, start=2):
        query_id = row["query_id"]
        require(
            OPAQUE_ID.fullmatch(query_id) is not None,
            f"synthetic-query-counts.csv:{line_number}: query_id is not opaque q_####",
        )
        n_control = integer_value(
            row["n_control"], location=f"synthetic-query-counts.csv:{line_number}:n_control"
        )
        y_control = integer_value(
            row["y_control"], location=f"synthetic-query-counts.csv:{line_number}:y_control"
        )
        n_treatment = integer_value(
            row["n_treatment"], location=f"synthetic-query-counts.csv:{line_number}:n_treatment"
        )
        y_treatment = integer_value(
            row["y_treatment"], location=f"synthetic-query-counts.csv:{line_number}:y_treatment"
        )
        token_count = integer_value(
            row["token_count"], location=f"synthetic-query-counts.csv:{line_number}:token_count"
        )
        require(n_control > 0 and n_treatment > 0, f"{query_id}: both randomized arms must be represented")
        require(y_control <= n_control, f"{query_id}: y_control exceeds n_control")
        require(y_treatment <= n_treatment, f"{query_id}: y_treatment exceeds n_treatment")
        require(token_count > 0, f"{query_id}: token_count must be positive")
        has_zero_success_cell |= y_control == 0 or y_treatment == 0
        has_all_success_cell |= y_control == n_control or y_treatment == n_treatment
        has_single_observation_cell |= n_control == 1 or n_treatment == 1

        weight = decimal_value(
            row["traffic_weight"],
            location=f"synthetic-query-counts.csv:{line_number}:traffic_weight",
        )
        cost = decimal_value(
            row["cost_outcome_units"],
            location=f"synthetic-query-counts.csv:{line_number}:cost_outcome_units",
        )
        require(weight > 0 and weight <= 1, f"{query_id}: traffic_weight must be in (0, 1]")
        require(cost >= 0, f"{query_id}: cost_outcome_units must be nonnegative")
        total_weight += weight
        numeric_by_id[query_id] = {"weight": weight, "cost": cost}

    require(total_weight == Decimal("1"), "synthetic count traffic weights must sum exactly to 1")
    require(has_zero_success_cell, "synthetic counts must exercise a y=0 boundary cell")
    require(has_all_success_cell, "synthetic counts must exercise a y=n boundary cell")
    require(has_single_observation_cell, "synthetic counts must exercise an n=1 cell")
    return rows, numeric_by_id


def validate_truth(
    count_rows: list[dict[str, str]],
    count_values: dict[str, dict[str, Decimal]],
) -> tuple[Decimal, Decimal]:
    rows = read_csv("fixtures/synthetic-known-truth.csv", TRUTH_HEADER)
    require(
        [row["query_id"] for row in rows] == [row["query_id"] for row in count_rows],
        "known-truth IDs and order must exactly match the count fixture",
    )
    weighted_delta = Decimal("0")
    weighted_tau = Decimal("0")
    truth_weight = Decimal("0")
    for line_number, row in enumerate(rows, start=2):
        query_id = row["query_id"]
        require(
            OPAQUE_ID.fullmatch(query_id) is not None,
            f"synthetic-known-truth.csv:{line_number}: query_id is not opaque q_####",
        )
        p_control = decimal_value(
            row["p_control_true"],
            location=f"synthetic-known-truth.csv:{line_number}:p_control_true",
        )
        p_treatment = decimal_value(
            row["p_treatment_true"],
            location=f"synthetic-known-truth.csv:{line_number}:p_treatment_true",
        )
        delta = decimal_value(
            row["delta_gross_true"],
            location=f"synthetic-known-truth.csv:{line_number}:delta_gross_true",
        )
        cost = decimal_value(
            row["cost_outcome_units"],
            location=f"synthetic-known-truth.csv:{line_number}:cost_outcome_units",
        )
        tau = decimal_value(
            row["tau_net_true"],
            location=f"synthetic-known-truth.csv:{line_number}:tau_net_true",
        )
        weight = decimal_value(
            row["traffic_weight"],
            location=f"synthetic-known-truth.csv:{line_number}:traffic_weight",
        )
        require(Decimal("0") <= p_control <= Decimal("1"), f"{query_id}: invalid p_control_true")
        require(Decimal("0") <= p_treatment <= Decimal("1"), f"{query_id}: invalid p_treatment_true")
        require(abs(delta - (p_treatment - p_control)) <= TOLERANCE, f"{query_id}: gross-effect truth identity failed")
        require(abs(tau - (delta - cost)) <= TOLERANCE, f"{query_id}: net-effect truth identity failed")
        require(cost == count_values[query_id]["cost"], f"{query_id}: truth/count cost mismatch")
        require(weight == count_values[query_id]["weight"], f"{query_id}: truth/count weight mismatch")
        truth_weight += weight
        weighted_delta += weight * delta
        weighted_tau += weight * tau

    require(truth_weight == Decimal("1"), "known-truth traffic weights must sum exactly to 1")
    return weighted_delta, weighted_tau


def validate_audit(required_checks: tuple[str, ...]) -> None:
    audit = load_json("fixtures/prerequisite-audit.pass.json")
    require(isinstance(audit, dict), "prerequisite audit must be a JSON object")
    require(audit.get("schema_version") == "1.0", "prerequisite audit schema_version must be 1.0")
    require(audit.get("scope") == "synthetic_fixture", "passing fixture audit must be synthetic_fixture")
    require(
        audit.get("analysis_population") == "first_shadow_trigger_positive",
        "fixture audit has the wrong analysis population",
    )
    require(audit.get("outcome_family") == "binary", "fixture audit outcome must be binary")
    checks = audit.get("checks")
    require(isinstance(checks, dict), "prerequisite audit checks must be an object")
    require(tuple(checks) == required_checks, "prerequisite audit check names/order do not match the schema")
    for check_name, item in checks.items():
        require(isinstance(item, dict), f"{check_name}: audit item must be an object")
        require(set(item) == {"status", "evidence_id", "note"}, f"{check_name}: audit item fields are not exact")
        require(item["status"] == "PASS", f"{check_name}: synthetic passing audit is not PASS")
        require(item["evidence_id"] == "SYNTHETIC_FIXTURE", f"{check_name}: unexpected fixture evidence ID")
        require(isinstance(item["note"], str) and item["note"].strip(), f"{check_name}: note is empty")


def validate_manifest_and_aggregation(count_rows: list[dict[str, str]]) -> None:
    manifest = load_json("fixtures/analysis-manifest.synthetic.json")
    aggregation = load_json("fixtures/aggregation-audit.synthetic.json")
    require(isinstance(manifest, dict), "synthetic analysis manifest must be an object")
    require(isinstance(aggregation, dict), "synthetic aggregation audit must be an object")
    require(
        manifest.get("schema_version") == "query_level_bayes.analysis_manifest.v1",
        "synthetic analysis manifest has the wrong version",
    )
    require(
        manifest.get("data_classification") == "synthetic",
        "synthetic analysis manifest has the wrong classification",
    )
    manifest_input = manifest.get("input", {})
    require(manifest_input.get("kind") == "query_counts_v1", "manifest input kind is wrong")
    require(manifest_input.get("row_count") == len(count_rows), "manifest row count is stale")
    counts_bytes = (ROOT / "fixtures/synthetic-query-counts.csv").read_bytes()
    observed_digest = hashlib.sha256(counts_bytes).hexdigest()
    require(
        manifest_input.get("content_sha256") == observed_digest,
        "manifest count-file digest is stale",
    )

    expected_sums = {
        "n_control": sum(int(row["n_control"]) for row in count_rows),
        "y_control": sum(int(row["y_control"]) for row in count_rows),
        "n_treatment": sum(int(row["n_treatment"]) for row in count_rows),
        "y_treatment": sum(int(row["y_treatment"]) for row in count_rows),
    }
    require(aggregation.get("state") == "PASS", "synthetic aggregation audit is not PASS")
    require(
        aggregation.get("retained_queries") == len(count_rows),
        "aggregation retained-query count is stale",
    )
    require(
        aggregation.get("final_sums") == expected_sums,
        "aggregation final arm sums are stale",
    )
    require(
        aggregation.get("actual_delivery_used_for_selection") is False,
        "aggregation audit must not select on actual delivery",
    )


def validate_configs(weighted_delta: Decimal, weighted_tau: Decimal) -> None:
    synthetic = load_json("config/synthetic.example.json")
    production = load_json("config/production.template.json")
    require(isinstance(synthetic, dict), "synthetic config must be an object")
    require(isinstance(production, dict), "production template must be an object")
    require(synthetic.get("run_mode") == "synthetic", "synthetic config has the wrong mode")
    require(
        synthetic.get("estimators") == ["empirical_bayes", "full_bayes"],
        "synthetic config must request both estimators in the declared order",
    )
    require(
        synthetic.get("summary", {}).get("interval_levels") == [0.5, 0.8, 0.95]
        and synthetic.get("summary", {}).get("paired_effect_draws") == 10000,
        "synthetic summary configuration is incomplete",
    )
    expected_cohort = {
        "primary_population": "first_shadow_trigger_positive",
        "required_shadow_value": 1,
        "use_actual_delivery_for_selection": False,
        "require_one_assignment_probability": True,
        "require_one_primary_contribution_per_user": True,
    }
    require(
        synthetic.get("cohort") == expected_cohort,
        "synthetic config changed the fixed cohort contract",
    )
    require(
        synthetic.get("analysis_manifest_file") == "fixtures/analysis-manifest.synthetic.json",
        "synthetic config has the wrong manifest path",
    )
    require(
        synthetic.get("aggregation_audit_file") == "fixtures/aggregation-audit.synthetic.json",
        "synthetic config has the wrong aggregation-audit path",
    )
    require(
        synthetic.get("decision_policy", {}).get("enabled") is False,
        "synthetic decision policy must be disabled",
    )
    require(
        synthetic.get("full_bayes", {}).get("robust_sensitivity_student_df") == 4.0
        and synthetic.get("full_bayes", {}).get("robust_sensitivity_approved") is True,
        "synthetic full-Bayes robust sensitivity must use approved fixed nu=4",
    )
    synthetic_priors = synthetic.get("full_bayes", {}).get("priors", {})
    require(
        isinstance(synthetic_priors, dict)
        and synthetic_priors.get("alpha_normal", {}).get("mean") is not None
        and synthetic_priors.get("alpha_normal", {}).get("sd") is not None
        and synthetic_priors.get("beta_normal", {}).get("mean") is not None
        and synthetic_priors.get("beta_normal", {}).get("sd") is not None
        and all(
            synthetic_priors.get(name) is not None
            for name in (
                "gamma0_normal_sd",
                "gamma_tau_normal_sd",
                "sigma0_half_normal_scale",
                "sigma_tau_half_normal_scale",
                "lkj_eta",
            )
        ),
        "synthetic full-Bayes priors must be explicit",
    )
    sensitivity_basis = synthetic.get("query_length", {}).get("sensitivity_basis", {})
    require(
        sensitivity_basis.get("kind") == "natural_spline"
        and sensitivity_basis.get("degree") == 3
        and sensitivity_basis.get("interior_knot_quantiles") == [0.25, 0.5, 0.75]
        and sensitivity_basis.get("approved_before_outcome_review") is True,
        "synthetic query-length sensitivity must be fully specified",
    )
    require(
        synthetic.get("synthetic_validation", {}).get("scope")
        == "synthetic_fixture_only_not_production_defaults"
        and isinstance(
            synthetic.get("synthetic_validation", {})
            .get("calibration", {})
            .get("maximum_absolute_overall_coverage_error"),
            (int, float),
        ),
        "synthetic validation tolerances must be explicit and synthetic-only",
    )
    require(
        synthetic.get("diagnostic_gates")
        == {
            "max_rhat_exclusive": 1.01,
            "min_bulk_ess_exclusive": 400,
            "min_tail_ess_exclusive": 400,
            "max_divergences": 0,
        },
        "synthetic diagnostic gates changed",
    )
    expected = synthetic.get("expected_truth", {})
    expected_delta = Decimal(str(expected.get("traffic_weighted_delta_gross")))
    expected_tau = Decimal(str(expected.get("traffic_weighted_tau_net")))
    require(abs(expected_delta - weighted_delta) <= TOLERANCE, "synthetic expected weighted gross truth is wrong")
    require(abs(expected_tau - weighted_tau) <= TOLERANCE, "synthetic expected weighted net truth is wrong")

    require(production.get("run_mode") == "production", "production template has the wrong mode")
    require(
        production.get("summary", {}).get("interval_levels") == [0.5, 0.8, 0.95]
        and production.get("summary", {}).get("paired_effect_draws") is None,
        "production summary template must preserve levels without inventing draw count",
    )
    require(
        production.get("cohort") == expected_cohort,
        "production template changed the fixed cohort contract",
    )
    require(
        production.get("production_execution_authorized") is False,
        "production template must not authorize execution",
    )
    require(
        production.get("approved_restricted_output_directory") is None,
        "production template must not contain an output path",
    )
    require(
        production.get("analysis_manifest_file") is None
        and production.get("aggregation_audit_file") is None,
        "production template must not contain input audit paths",
    )
    require(
        production.get("cost", {}).get("value") is None,
        "production template must not invent a cost value",
    )
    require(
        production.get("decision_policy", {}).get("enabled") is False,
        "production decision policy must be disabled",
    )
    require(
        production.get("full_bayes", {}).get("robust_sensitivity_student_df") == 4.0
        and production.get("full_bayes", {}).get("robust_sensitivity_approved") is False,
        "production robust sensitivity must remain fixed at nu=4 and unapproved",
    )
    production_priors = production.get("full_bayes", {}).get("priors", {})
    require(
        production_priors.get("alpha_normal", {}).get("mean") is None
        and production_priors.get("alpha_normal", {}).get("sd") is None
        and production_priors.get("beta_normal", {}).get("mean") is None
        and production_priors.get("beta_normal", {}).get("sd") is None
        and all(
            production_priors.get(name) is None
            for name in (
                "gamma0_normal_sd",
                "gamma_tau_normal_sd",
                "sigma0_half_normal_scale",
                "sigma_tau_half_normal_scale",
                "lkj_eta",
            )
        ),
        "production template must not invent prior values",
    )
    require(
        production.get("validation", {}).get("approved_before_outcome_review") is False
        and production.get("validation", {}).get("coverage_tolerances") is None
        and production.get("validation", {}).get("cross_method_disagreement_tolerances")
        is None,
        "production validation tolerances must remain unapproved placeholders",
    )
    require(
        production.get("diagnostic_gates")
        == {
            "max_rhat_exclusive": 1.01,
            "min_bulk_ess_exclusive": 400,
            "min_tail_ess_exclusive": 400,
            "max_divergences": 0,
        },
        "production diagnostic gates changed",
    )


def compile_starter() -> None:
    path = ROOT / "starter/interfaces.py"
    source = path.read_text(encoding="utf-8")
    try:
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        raise CheckError(f"starter/interfaces.py does not compile: {exc}") from exc


def scan_text_files() -> None:
    mac_home_marker = "/" + "Users" + "/"
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    secret_patterns = (
        ("private key", re.compile(re.escape(private_key_marker))),
        ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("GitHub token", re.compile(r"\bghp_[A-Za-z0-9]{30,}\b")),
        ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
        ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
        ("generic API token", re.compile(r"\bsk-[A-Za-z0-9]{24,}\b")),
        (
            "credential assignment",
            re.compile(
                r"(?i)\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)"
                r"\b\s*[:=]\s*[\"'][^\"']{8,}[\"']"
            ),
        ),
        (
            "credential-bearing URL",
            re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"),
        ),
    )
    placeholders = ("NOT_PROVIDED", "SYNTHETIC_FIXTURE")
    forbidden_binary_suffixes = {
        ".arrow",
        ".feather",
        ".nc",
        ".netcdf",
        ".parquet",
        ".pyc",
        ".zip",
    }
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        require(
            path.suffix.lower() not in forbidden_binary_suffixes,
            f"{relative}: binary/data artifacts are forbidden inside the package",
        )
        if path.suffix.lower() == ".csv":
            require(
                relative.parts
                in {
                    ("fixtures", "synthetic-query-counts.csv"),
                    ("fixtures", "synthetic-known-truth.csv"),
                },
                f"{relative}: only reviewed synthetic fixture CSVs may be committed",
            )
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise CheckError(f"{relative}: non-UTF-8/binary file is forbidden") from exc
        require(mac_home_marker not in text, f"{relative}: contains an absolute macOS home path")
        for label, pattern in secret_patterns:
            for match in pattern.finditer(text):
                matched = match.group(0)
                if any(placeholder in matched for placeholder in placeholders):
                    continue
                raise CheckError(f"{relative}: possible {label}")


def main() -> int:
    validate_required_files()
    required_checks = validate_schemas()
    count_schema = load_json("schemas/query-counts.schema.json")
    count_header = tuple(count_schema["x-csv-header"])
    count_rows, count_values = validate_counts(count_header)
    weighted_delta, weighted_tau = validate_truth(count_rows, count_values)
    validate_audit(required_checks)
    validate_manifest_and_aggregation(count_rows)
    validate_configs(weighted_delta, weighted_tau)
    compile_starter()
    scan_text_files()
    print("PASS: query-level-bayes scaffold integrity checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
