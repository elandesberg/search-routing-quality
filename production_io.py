"""Validated production I/O and bounded feature design for allowlist estimators."""

from __future__ import annotations

import csv
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np


REQUIRED_COUNT_COLUMNS = ("query_id", "n0", "c0", "n1", "c1")
FEATURE_RE = re.compile(r"^f([1-9][0-9]*)$")
DEFAULT_MAX_BASIS_TERMS = 5_000


class DataValidationError(ValueError):
    """Raised when production input is empty, malformed, or internally invalid."""


@dataclass(frozen=True)
class AllowlistData:
    ids: tuple[str, ...]
    n0: np.ndarray
    c0: np.ndarray
    n1: np.ndarray
    c1: np.ndarray
    feature_names: tuple[str, ...]
    features: np.ndarray


@dataclass(frozen=True)
class CandidateData:
    ids: tuple[str, ...]
    feature_names: tuple[str, ...]
    features: np.ndarray


@dataclass(frozen=True)
class FeatureDesign:
    """A fitted standardization and deterministic linear/quadratic basis."""

    mean: np.ndarray
    scale: np.ndarray
    quadratic: bool = False
    max_terms: int = DEFAULT_MAX_BASIS_TERMS

    @classmethod
    def fit(
        cls,
        features: np.ndarray,
        *,
        quadratic: bool = False,
        max_terms: int = DEFAULT_MAX_BASIS_TERMS,
    ) -> "FeatureDesign":
        x = _as_feature_matrix(features)
        if max_terms < 1:
            raise DataValidationError("max_terms must be at least 1")
        term_count = basis_term_count(x.shape[1], quadratic=quadratic)
        if term_count > max_terms:
            raise DataValidationError(
                f"requested basis has {term_count:,} terms, exceeding the "
                f"--max-basis-terms guard ({max_terms:,}); use the default "
                "linear design or reduce the feature dimension"
            )
        mean = x.mean(axis=0)
        scale = x.std(axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
        return cls(mean=mean, scale=scale, quadratic=quadratic, max_terms=max_terms)

    def standardized(self, features: np.ndarray) -> np.ndarray:
        x = _as_feature_matrix(features)
        if x.shape[1] != len(self.mean):
            raise DataValidationError(
                f"feature dimension mismatch: expected {len(self.mean)}, got {x.shape[1]}"
            )
        return (x - self.mean) / self.scale

    def transform(self, features: np.ndarray) -> np.ndarray:
        z = self.standardized(features)
        term_count = basis_term_count(z.shape[1], quadratic=self.quadratic)
        if term_count > self.max_terms:
            raise DataValidationError(
                f"basis has {term_count:,} terms, above guard {self.max_terms:,}"
            )
        columns = [np.ones((len(z), 1)), z]
        if self.quadratic:
            columns.append(z**2)
            columns.extend(
                (z[:, i] * z[:, j])[:, None]
                for i in range(z.shape[1])
                for j in range(i + 1, z.shape[1])
            )
        return np.hstack(columns)


def basis_term_count(raw_dimension: int, *, quadratic: bool) -> int:
    if raw_dimension < 1:
        raise DataValidationError("at least one numeric feature column is required")
    if not quadratic:
        return 1 + raw_dimension
    return 1 + 2 * raw_dimension + raw_dimension * (raw_dimension - 1) // 2


def load_allowlist_csv(path: str | os.PathLike[str]) -> AllowlistData:
    fieldnames, rows = _read_csv(path)
    missing = [name for name in REQUIRED_COUNT_COLUMNS if name not in fieldnames]
    if missing:
        raise DataValidationError(f"missing required columns: {', '.join(missing)}")
    feature_names = _feature_names(fieldnames)
    ids = _validated_ids(rows)
    n0 = _integer_column(rows, "n0")
    c0 = _integer_column(rows, "c0")
    n1 = _integer_column(rows, "n1")
    c1 = _integer_column(rows, "c1")
    for conversions, sessions, arm in ((c0, n0, "control"), (c1, n1, "treatment")):
        invalid = np.flatnonzero((conversions < 0) | (sessions < 0) | (conversions > sessions))
        if len(invalid):
            row = int(invalid[0]) + 2
            raise DataValidationError(
                f"row {row}: {arm} counts must satisfy 0 <= conversions <= sessions"
            )
    features = _feature_matrix(rows, feature_names)
    return AllowlistData(ids, n0, c0, n1, c1, feature_names, features)


def load_candidate_csv(
    path: str | os.PathLike[str],
    expected_features: Sequence[str],
) -> CandidateData:
    fieldnames, rows = _read_csv(path)
    if "query_id" not in fieldnames:
        raise DataValidationError("candidate file is missing required column: query_id")
    unexpected = [
        name for name in fieldnames if name not in {"query_id", *expected_features}
    ]
    if unexpected:
        raise DataValidationError(
            "candidate file may contain only query_id and the training features; "
            f"unexpected columns: {unexpected}"
        )
    feature_names = _feature_names(fieldnames)
    expected = tuple(expected_features)
    if feature_names != expected:
        raise DataValidationError(
            "candidate feature columns must exactly match training columns in order: "
            f"expected {list(expected)}, got {list(feature_names)}"
        )
    ids = _validated_ids(rows)
    features = _feature_matrix(rows, feature_names)
    return CandidateData(ids, feature_names, features)


def support_distances(
    training_standardized: np.ndarray,
    candidate_standardized: np.ndarray,
) -> tuple[np.ndarray, float, np.ndarray]:
    """Return nearest-neighbor distances and a labeled heuristic support flag.

    The threshold is the 95th percentile of each training row's distance to its
    nearest *other* training row. This is a geometry heuristic, not a confidence
    interval or a causal-overlap guarantee.
    """

    from scipy.spatial import cKDTree

    train = _as_feature_matrix(training_standardized)
    cand = _as_feature_matrix(candidate_standardized)
    if train.shape[1] != cand.shape[1]:
        raise DataValidationError("candidate and training feature dimensions differ")
    tree = cKDTree(train)
    distances = np.asarray(tree.query(cand, k=1)[0], dtype=float)
    if len(train) < 2:
        threshold = 0.0
    else:
        nearest_other = np.asarray(tree.query(train, k=2)[0][:, 1], dtype=float)
        threshold = float(np.quantile(nearest_other, 0.95))
    return distances, threshold, distances <= threshold


def posterior_rows(
    ids: Sequence[str],
    tau_mean: np.ndarray,
    tau_sd: np.ndarray,
    p_neg: np.ndarray,
) -> Iterable[Mapping[str, object]]:
    if not (len(ids) == len(tau_mean) == len(tau_sd) == len(p_neg)):
        raise ValueError("posterior output lengths do not match")
    if not (
        np.isfinite(tau_mean).all()
        and np.isfinite(tau_sd).all()
        and np.isfinite(p_neg).all()
        and np.all(np.asarray(tau_sd) >= 0)
        and np.all((np.asarray(p_neg) >= 0) & (np.asarray(p_neg) <= 1))
    ):
        raise ValueError("posterior outputs must be finite with valid scales and probabilities")
    for i, query_id in enumerate(ids):
        probability = float(p_neg[i])
        # These literal probability bins are descriptive QA aids, not policy
        # recommendations. Production action thresholds require separate human
        # approval and should be applied downstream to the continuous p_neg.
        if probability > 0.8:
            diagnostic_band = "non_action__p_neg_gt_0.80"
        elif probability > 0.6:
            diagnostic_band = "non_action__p_neg_gt_0.60_le_0.80"
        else:
            diagnostic_band = "non_action__p_neg_le_0.60"
        yield {
            "query_id": query_id,
            "tau_mean": f"{float(tau_mean[i]):.8g}",
            "tau_sd": f"{float(tau_sd[i]):.8g}",
            "p_neg": f"{probability:.8g}",
            "diagnostic_p_neg_band": diagnostic_band,
        }


def candidate_rows(
    ids: Sequence[str],
    mean: np.ndarray,
    p_pos: np.ndarray,
    distances: np.ndarray,
    threshold: float,
    in_support: np.ndarray,
) -> Iterable[Mapping[str, object]]:
    if not (len(ids) == len(mean) == len(p_pos) == len(distances) == len(in_support)):
        raise ValueError("candidate output lengths do not match")
    if not (
        np.isfinite(mean).all()
        and np.isfinite(p_pos).all()
        and np.isfinite(distances).all()
        and np.isfinite(threshold)
        and np.all((np.asarray(p_pos) >= 0) & (np.asarray(p_pos) <= 1))
        and np.all(np.asarray(distances) >= 0)
        and threshold >= 0
    ):
        raise ValueError("candidate outputs must be finite with valid probabilities and distances")
    eligible = np.flatnonzero(np.asarray(in_support, dtype=bool))
    eligible_order = eligible[np.argsort(-np.asarray(mean)[eligible])]
    ranks: list[object] = [""] * len(ids)
    for rank, index in enumerate(eligible_order, start=1):
        ranks[int(index)] = rank
    for i, query_id in enumerate(ids):
        yield {
            "query_id": query_id,
            "rank_within_near_support": ranks[i],
            "tau_mean_predictive": f"{float(mean[i]):.8g}",
            "p_net_positive_predictive": f"{float(p_pos[i]):.8g}",
            "support_distance_nearest_standardized": f"{float(distances[i]):.8g}",
            "support_threshold_training_nn_p95": f"{float(threshold):.8g}",
            "support_flag_heuristic": "near_support" if bool(in_support[i]) else "extrapolation",
        }


def write_csv_atomic(
    path: str | os.PathLike[str],
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temporary_name = handle.name
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        raise


def archive_existing_outputs(
    *paths: str | os.PathLike[str],
    protected_paths: Sequence[str | os.PathLike[str] | None] = (),
) -> tuple[tuple[Path, Path], ...]:
    """Move prior outputs aside before a run, preserving them as stale artifacts.

    This makes a failed rerun fail closed: the conventional output path is
    absent, while the prior file remains recoverable under an explicit
    ``.stale-<UTC timestamp>`` name in the same directory.
    """

    protected = {
        Path(path).resolve(strict=False)
        for path in protected_paths
        if path is not None
    }
    targets: list[Path] = []
    seen: set[Path] = set()
    for value in paths:
        target = Path(value)
        resolved = target.resolve(strict=False)
        if resolved in protected:
            raise DataValidationError(
                f"output path must not overwrite an input file: {target}"
            )
        if resolved in seen:
            raise DataValidationError(f"output paths must be distinct: {target}")
        seen.add(resolved)
        if target.exists() and not target.is_file():
            raise DataValidationError(
                f"output target exists but is not a regular file: {target}"
            )
        targets.append(target)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    moves: list[tuple[Path, Path]] = []
    for target in targets:
        if not target.exists():
            continue
        candidate = target.with_name(
            f"{target.stem}.stale-{timestamp}{target.suffix}"
        )
        suffix = 1
        while candidate.exists():
            candidate = target.with_name(
                f"{target.stem}.stale-{timestamp}-{suffix}{target.suffix}"
            )
            suffix += 1
        os.replace(target, candidate)
        moves.append((target, candidate))
    return tuple(moves)


def _read_csv(path: str | os.PathLike[str]) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    source = Path(path)
    try:
        handle = source.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise DataValidationError(f"cannot read {source}: {exc}") from exc
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise DataValidationError(f"{source} is empty or has no header")
        fieldnames = tuple(reader.fieldnames)
        if any(name is None or not name.strip() for name in fieldnames):
            raise DataValidationError("CSV header contains an empty column name")
        if len(set(fieldnames)) != len(fieldnames):
            raise DataValidationError("CSV header contains duplicate column names")
        rows = list(reader)
    if not rows:
        raise DataValidationError(f"{source} contains no data rows")
    if any(None in row for row in rows):
        raise DataValidationError("a row has more values than the CSV header")
    return fieldnames, rows


def _feature_names(fieldnames: Sequence[str]) -> tuple[str, ...]:
    found: list[tuple[int, str]] = []
    unexpected: list[str] = []
    reserved = set(REQUIRED_COUNT_COLUMNS)
    for name in fieldnames:
        if name in reserved:
            continue
        match = FEATURE_RE.fullmatch(name)
        if match:
            found.append((int(match.group(1)), name))
        else:
            unexpected.append(name)
    if unexpected:
        raise DataValidationError(
            "unexpected columns; numeric features must be named f1..fK: "
            + ", ".join(unexpected)
        )
    found.sort()
    if not found:
        raise DataValidationError("at least one numeric feature column f1..fK is required")
    numbers = [number for number, _ in found]
    expected = list(range(1, len(found) + 1))
    if numbers != expected:
        raise DataValidationError(
            f"feature columns must be contiguous f1..fK; found {[name for _, name in found]}"
        )
    return tuple(name for _, name in found)


def _validated_ids(rows: Sequence[Mapping[str, str]]) -> tuple[str, ...]:
    ids: list[str] = []
    seen: set[str] = set()
    for offset, row in enumerate(rows, start=2):
        value = row.get("query_id")
        if value is None or not value.strip():
            raise DataValidationError(f"row {offset}: query_id is empty")
        if value in seen:
            raise DataValidationError(f"row {offset}: duplicate query_id {value!r}")
        seen.add(value)
        ids.append(value)
    return tuple(ids)


def _integer_column(rows: Sequence[Mapping[str, str]], name: str) -> np.ndarray:
    values: list[int] = []
    for offset, row in enumerate(rows, start=2):
        raw = row.get(name)
        if raw is None:
            raise DataValidationError(f"row {offset}: {name} must be an integer")
        try:
            value = int(raw)
        except ValueError as exc:
            raise DataValidationError(f"row {offset}: {name} must be an integer") from exc
        if str(value) != raw.strip():
            raise DataValidationError(f"row {offset}: {name} must be an integer")
        values.append(value)
    return np.asarray(values, dtype=np.int64)


def _feature_matrix(
    rows: Sequence[Mapping[str, str]],
    feature_names: Sequence[str],
) -> np.ndarray:
    matrix = np.empty((len(rows), len(feature_names)), dtype=float)
    for row_index, row in enumerate(rows):
        for column_index, name in enumerate(feature_names):
            raw = row.get(name)
            try:
                value = float(raw) if raw is not None else math.nan
            except ValueError as exc:
                raise DataValidationError(
                    f"row {row_index + 2}: {name} must be numeric"
                ) from exc
            if not math.isfinite(value):
                raise DataValidationError(f"row {row_index + 2}: {name} must be finite")
            matrix[row_index, column_index] = value
    return matrix


def _as_feature_matrix(features: np.ndarray) -> np.ndarray:
    matrix = np.asarray(features, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 1 or matrix.shape[1] < 1:
        raise DataValidationError("features must be a non-empty two-dimensional matrix")
    if not np.isfinite(matrix).all():
        raise DataValidationError("features must contain only finite values")
    return matrix
