import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from production_io import (
    DataValidationError,
    FeatureDesign,
    archive_existing_outputs,
    candidate_rows,
    load_allowlist_csv,
    posterior_rows,
    write_csv_atomic,
)
from synthetic_benchmarks import (
    fit_gaussian_eb,
    fit_robust_irls_negative_benchmark,
)


class ProductionInputTests(unittest.TestCase):
    def write(self, directory, name, contents):
        path = Path(directory) / name
        path.write_text(contents, encoding="utf-8")
        return path

    def test_empty_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, "empty.csv", "query_id,n0,c0,n1,c1,f1\n")
            with self.assertRaisesRegex(DataValidationError, "no data rows"):
                load_allowlist_csv(path)

    def test_invalid_counts_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(
                directory,
                "bad.csv",
                "query_id,n0,c0,n1,c1,f1\nq1,10,11,10,1,0.5\n",
            )
            with self.assertRaisesRegex(DataValidationError, "conversions <= sessions"):
                load_allowlist_csv(path)

    def test_csv_writer_round_trips_comma_id(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "posteriors.csv"
            write_csv_atomic(
                output,
                (
                    "query_id",
                    "tau_mean",
                    "tau_sd",
                    "p_neg",
                    "diagnostic_p_neg_band",
                ),
                posterior_rows(
                    ("brand, model",),
                    np.array([0.01]),
                    np.array([0.002]),
                    np.array([0.9]),
                ),
            )
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["query_id"], "brand, model")
            self.assertEqual(
                rows[0]["diagnostic_p_neg_band"],
                "non_action__p_neg_gt_0.80",
            )

    def test_existing_output_is_archived_non_destructively(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "posteriors.csv"
            output.write_text("prior run\n", encoding="utf-8")
            moves = archive_existing_outputs(output)
            self.assertFalse(output.exists())
            self.assertEqual(len(moves), 1)
            self.assertEqual(moves[0][1].read_text(encoding="utf-8"), "prior run\n")
            self.assertIn(".stale-", moves[0][1].name)


class FeatureDesignTests(unittest.TestCase):
    def test_standardized_linear_is_default_and_has_intercept(self):
        x = np.array([[1.0, 4.0], [2.0, 4.0], [3.0, 4.0]])
        design = FeatureDesign.fit(x)
        transformed = design.transform(x)
        self.assertEqual(transformed.shape, (3, 3))
        np.testing.assert_allclose(transformed[:, 0], 1.0)
        np.testing.assert_allclose(transformed[:, 1:].mean(axis=0), 0.0, atol=1e-12)
        self.assertTrue(np.isfinite(transformed).all())

    def test_quadratic_dimension_is_explicit_and_guarded(self):
        x = np.arange(12, dtype=float).reshape(4, 3)
        design = FeatureDesign.fit(x, quadratic=True, max_terms=10)
        self.assertEqual(design.transform(x).shape, (4, 10))
        with self.assertRaisesRegex(DataValidationError, "exceeding"):
            FeatureDesign.fit(np.ones((2, 100)), quadratic=True, max_terms=100)

    def test_candidates_are_ranked_only_within_near_support(self):
        rows = list(
            candidate_rows(
                ("near-low", "outside-high", "near-high"),
                np.array([0.01, 0.99, 0.02]),
                np.array([0.7, 0.99, 0.8]),
                np.array([0.1, 9.0, 0.2]),
                0.5,
                np.array([True, False, True]),
            )
        )
        self.assertEqual(rows[2]["rank_within_near_support"], 1)
        self.assertEqual(rows[0]["rank_within_near_support"], 2)
        self.assertEqual(rows[1]["rank_within_near_support"], "")
        self.assertEqual(rows[1]["support_flag_heuristic"], "extrapolation")


class SparseEmpiricalBayesTests(unittest.TestCase):
    def test_sparse_data_keeps_prior_variance_instead_of_crashing(self):
        n0 = np.ones(4, dtype=int)
        n1 = np.ones(4, dtype=int)
        c0 = np.zeros(4, dtype=int)
        c1 = np.zeros(4, dtype=int)
        features = np.column_stack([np.ones(4), np.arange(4, dtype=float)])
        for estimator in (
            fit_gaussian_eb,
            fit_robust_irls_negative_benchmark,
        ):
            with self.subTest(estimator=estimator.__name__):
                result = estimator(n0, c0, n1, c1, features)
                self.assertTrue(np.isfinite(result["p_neg"]).all())
                self.assertTrue(np.isfinite(result["tau_mean"]).all())


if __name__ == "__main__":
    unittest.main()
