import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

import allowlist_model_pymc


def write_training_csv(path, ids=("q1", "q2")):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["query_id", "n0", "c0", "n1", "c1", "f1"])
        writer.writerow([ids[0], 20, 1, 20, 2, 0.0])
        writer.writerow([ids[1], 20, 2, 20, 1, 1.0])


class PyMCFailClosedTests(unittest.TestCase):
    def fake_result(self, *, rhat=1.0, ess=500.0, divergences=0):
        return {
            "p_neg": np.array([0.9, 0.1]),
            "tau_mean": np.array([-0.01, 0.02]),
            "tau_sd": np.array([0.003, 0.004]),
            "student_df": 4.0,
            "sigma_u": 0.1,
            "rhat_max": rhat,
            "ess_min": ess,
            "divergences": divergences,
        }

    def test_bad_diagnostics_archive_prior_and_write_no_current_output(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "logs.csv"
            output = Path(directory) / "posteriors.csv"
            write_training_csv(data)
            output.write_text("prior successful run\n", encoding="utf-8")

            def bad_fit(*args, **kwargs):
                return self.fake_result(rhat=1.2)

            with self.assertRaises(allowlist_model_pymc.DiagnosticsError):
                allowlist_model_pymc.production(
                    data, 0.002, output=output, fit_fn=bad_fit, progressbar=False
                )
            self.assertFalse(output.exists())
            stale = list(Path(directory).glob("posteriors.stale-*.csv"))
            self.assertEqual(len(stale), 1)
            self.assertEqual(
                stale[0].read_text(encoding="utf-8"),
                "prior successful run\n",
            )

    def test_acceptance_boundaries_are_strict(self):
        with self.assertRaises(allowlist_model_pymc.DiagnosticsError):
            allowlist_model_pymc.enforce_diagnostics(1.01, 401, 0)
        with self.assertRaises(allowlist_model_pymc.DiagnosticsError):
            allowlist_model_pymc.enforce_diagnostics(1.009, 400, 0)

    def test_release_diagnostic_gates_cannot_be_weakened(self):
        weaker_settings = (
            {"max_rhat": 1.02},
            {"min_ess": 399},
            {"max_divergences": 1},
        )
        for settings in weaker_settings:
            with self.subTest(settings=settings):
                with self.assertRaisesRegex(
                    ValueError,
                    "may only tighten the release gates",
                ):
                    allowlist_model_pymc.enforce_diagnostics(
                        1.0,
                        500,
                        0,
                        **settings,
                    )

    def test_sampling_cores_must_be_within_chain_count(self):
        for invalid_cores in (0, 3):
            with self.subTest(cores=invalid_cores):
                with self.assertRaisesRegex(
                    ValueError,
                    "1 <= cores <= chains",
                ):
                    allowlist_model_pymc._validate_sampling_controls(
                        draws=10,
                        tune=10,
                        chains=2,
                        cores=invalid_cores,
                        target_accept=0.9,
                    )

    def test_student_df_is_prespecified_and_has_finite_variance(self):
        for invalid_df in (True, "4", 2.0, np.inf):
            with self.subTest(student_df=invalid_df):
                with self.assertRaisesRegex(
                    ValueError,
                    "student_df must be finite and greater than 2",
                ):
                    allowlist_model_pymc._validate_student_df(invalid_df)

    def test_direct_fit_rejects_fractional_counts_before_sampling(self):
        with self.assertRaisesRegex(
            ValueError,
            "n0 must contain finite integer-valued counts",
        ):
            allowlist_model_pymc.fit_pymc(
                np.array([10.5]),
                np.array([1]),
                np.array([10]),
                np.array([1]),
                np.ones((1, 1)),
                draws=1,
                tune=0,
                chains=2,
                cores=1,
                progressbar=False,
            )

    def test_good_diagnostics_preserve_quoted_query_id(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "logs.csv"
            output = Path(directory) / "posteriors.csv"
            write_training_csv(data, ids=("brand, model", "q2"))
            received = {}

            def good_fit(*args, **kwargs):
                received["cores"] = kwargs["cores"]
                received["student_df"] = kwargs["student_df"]
                return self.fake_result()

            allowlist_model_pymc.production(
                data, 0.002, output=output, fit_fn=good_fit, progressbar=False
            )
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["query_id"], "brand, model")
            self.assertEqual(len(rows[0]), 5)
            self.assertEqual(received["cores"], 1)
            self.assertEqual(received["student_df"], 4.0)


class SyntheticRecoveryTests(unittest.TestCase):
    def test_recovery_summary_is_descriptive_and_finite(self):
        world = {
            "n0": np.array([100, 100, 100, 100]),
            "c0": np.array([5, 5, 5, 5]),
            "n1": np.array([100, 100, 100, 100]),
            "c1": np.array([4, 5, 7, 8]),
            "F": np.column_stack([np.ones(4), np.array([-1.0, -0.2, 0.3, 1.0])]),
            "net_allowlist": np.array([-0.01, -0.002, 0.01, 0.02]),
            "net_candidates": np.array([-0.02, 0.01, 0.03]),
            "outlier_allowlist": np.array([True, False, False, False]),
        }
        posterior = {
            "tau_mean": np.array([-0.008, -0.001, 0.009, 0.018]),
            "tau_sd": np.full(4, 0.004),
            "p_neg": np.array([0.95, 0.6, 0.1, 0.01]),
            "cand_mean": np.array([-0.01, 0.008, 0.025]),
            "rhat_max": 1.005,
            "ess_min": 500.0,
            "divergences": 0,
            "student_df": 4.0,
        }
        summary = allowlist_model_pymc.synthetic_recovery_summary(
            posterior,
            world,
            top_k=2,
        )
        self.assertEqual(
            summary["scope"],
            "synthetic_only_not_production_evidence",
        )
        self.assertEqual(summary["automatic_gates"], "sampler_diagnostics_only")
        self.assertEqual(
            summary["candidate_truth_ranking"]["reported_top_k"],
            2,
        )
        self.assertGreater(
            summary["candidate_truth_ranking"]["top_k_mean_net_effect"],
            summary["candidate_truth_ranking"]["all_candidate_mean_net_effect"],
        )


if __name__ == "__main__":
    unittest.main()
