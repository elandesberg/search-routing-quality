# Release validation — 2026-07-26

This record applies only to the synthetic fixtures and package mechanics in
this commit. It is not production evidence, model approval, or permission to
change a routing policy.

## Locked environment

- CPython 3.12.9
- Exact dependencies from `requirements-lock.txt`
- `uv pip check`: all 39 installed packages compatible

## PyMC synthetic gate

Command:

```bash
python allowlist_model_pymc.py --demo --no-progress
```

The sole candidate production estimator used four sequential chains, 1,000
tuning iterations, and 1,000 retained draws per chain with prespecified
Student-t degrees of freedom 4.

| Diagnostic | Result | Gate |
|---|---:|---:|
| Maximum R-hat | 1.00895 | < 1.01 |
| Minimum bulk ESS | 624.6 | > 400 |
| Divergences | 0 | = 0 |

The known-truth metrics are descriptive, not acceptance thresholds. In this
fixture, the PyMC posterior means had 0.00901 RMSE, 81.0% sign accuracy, and
88.6% approximate 90% interval coverage. The top 300 predicted off-list
candidates were 93.7% truly net-positive, versus 46.5% across all candidates.

Important negative evidence: on the 62 injected outlier queries, sign accuracy
was 50.0%, approximate interval coverage was 33.9%, and mean error was +0.0180.
The Gaussian-EB orientation benchmark also had lower aggregate RMSE in this
particular fixture. Convergence therefore does not validate the production
model. `UNRESOLVED.md` blocks the Stage 2b fit until owners approve
prior-predictive behavior, the prespecified degrees-of-freedom sensitivity, and
a decision-stability criterion.

An attempted learned-degrees-of-freedom specification failed the unchanged
sampler gate (maximum R-hat 1.15, minimum bulk ESS 28, zero divergences). The
worst parameter was the weakly identified tail degree of freedom. It was
removed as an estimated nuisance parameter, not replaced with a more permissive
diagnostic threshold.

## Other checks

- 16 focused unit tests passed.
- Python compilation, Ruff correctness checks, and mypy passed.
- Both synthetic simulation scripts completed and reproduced the checked-in
  document values.
- The self-contained HTML passed structural checks: five figures, unique IDs,
  and light/dark theme support.
- Desktop, mobile, light-theme, and dark-theme renders were visually inspected.
- All 36 local Markdown/HTML targets resolved; the HTML has no external assets.
- No alternate sampler, second production estimator, credential-like content,
  symlink, or source file larger than 1 MB is present in the release source.
