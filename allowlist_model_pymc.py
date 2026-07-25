"""
Hierarchical Bayesian allowlist estimator — PyMC implementation (PRIMARY).

Same model as hier_bayes_allowlist.py (that file is the spec and the
validated cross-check; its custom Gibbs sampler exists because the authoring
sandbox had no PPL). Where PyMC is available, run THIS version: standard
API, maintained sampler (NUTS), and real convergence diagnostics.

  c0_q ~ Binomial(n0_q, sigmoid(alpha_q))
  c1_q ~ Binomial(n1_q, sigmoid(alpha_q + b_q))
  alpha_q = Phi_q @ gamma + sigma_a * a_raw_q,   a_raw ~ Normal(0, 1)
  b_q     = Phi_q @ beta  + sigma_u * u_raw_q,   u_raw ~ StudentT(nu, 0, 1)
  gamma, beta ~ Normal(0, 1);  sigma_a ~ HalfNormal(1.5);
  sigma_u ~ HalfNormal(0.3);   nu ~ Gamma(2, 0.1)   (continuous, unlike the
                                                     grid in the Gibbs version)

Non-centered parameterization throughout (avoids the funnel). Net effect per
query, on the probability scale, is computed from the posterior draws:
  tau_q = sigmoid(alpha_q + b_q) - sigmoid(alpha_q) - cost

STATUS: written against PyMC 5.x; syntax-checked but NOT executed in the
authoring environment (no PyMC there). FIRST RUN MUST BE THE CROSS-CHECK:
    python3 allowlist_model_pymc.py --demo
which fits the same synthetic world as hier_bayes_allowlist.py --demo and
prints decision agreement between the two samplers. Require >= 95% agreement
on P(net<0) > 0.8 decisions and consistent sigma_u / nu before using on real
data. Acceptance bars for any production run:
    max R-hat < 1.01 on hyperparameters, min bulk-ESS > 400, 0 divergences
(bump target_accept to 0.95+ if divergences appear).

USAGE
  cross-check:  python3 allowlist_model_pymc.py --demo [--outliers 0.03]
  production:   python3 allowlist_model_pymc.py --data logs.csv --cost 0.002
  logs.csv columns: query_id, n0, c0, n1, c1, f1..fK — same interface as
  hier_bayes_allowlist.py. Writes posteriors_pymc.csv.

Scaling notes: ~2k queries -> minutes on 4 chains. For 20k+ queries, try
  pm.sample(nuts_sampler="numpyro")  or  nutpie, and/or fewer draws; the
model's local parameters scale linearly and NUTS handles it, just more slowly
than the specialized Gibbs scheme.
"""
import numpy as np, argparse, time
from scipy.special import expit
from hier_bayes_allowlist import basis, make_world, fit_eb, fit as fit_gibbs, COST


def fit_pymc(n0, c0, n1, c1, F, cost=COST, draws=1000, tune=1000, chains=4,
             target_accept=0.9, seed=0, cand_F=None, nuts_sampler="pymc"):
    import pymc as pm
    import arviz as az
    NQ, K = F.shape
    with pm.Model() as model:
        gamma = pm.Normal("gamma", 0.0, 1.0, shape=K)
        beta = pm.Normal("beta", 0.0, 1.0, shape=K)
        sigma_a = pm.HalfNormal("sigma_a", 1.5)
        sigma_u = pm.HalfNormal("sigma_u", 0.3)
        nu = pm.Gamma("nu", 2.0, 0.1)
        a_raw = pm.Normal("a_raw", 0.0, 1.0, shape=NQ)
        u_raw = pm.StudentT("u_raw", nu=nu, mu=0.0, sigma=1.0, shape=NQ)
        alpha = pm.Deterministic("alpha", pm.math.dot(F, gamma) + sigma_a * a_raw)
        b = pm.Deterministic("b", pm.math.dot(F, beta) + sigma_u * u_raw)
        pm.Binomial("y0", n=n0, p=pm.math.invlogit(alpha), observed=c0)
        pm.Binomial("y1", n=n1, p=pm.math.invlogit(alpha + b), observed=c1)
        idata = pm.sample(draws=draws, tune=tune, chains=chains,
                          target_accept=target_accept, random_seed=seed,
                          nuts_sampler=nuts_sampler, progressbar=True)

    # ---- diagnostics gate ----
    hyper = ["gamma", "beta", "sigma_a", "sigma_u", "nu"]
    summ = az.summary(idata, var_names=hyper)
    rhat_max = float(summ["r_hat"].max())
    ess_min = float(summ["ess_bulk"].min())
    ndiv = int(idata.sample_stats["diverging"].values.sum())
    print(f"diagnostics: max R-hat {rhat_max:.4f} | min bulk-ESS {ess_min:.0f} | divergences {ndiv}")
    if rhat_max > 1.01 or ess_min < 400 or ndiv > 0:
        print("WARNING: diagnostics below acceptance bar — do not ship these lists; "
              "raise target_accept / draws, or investigate.")

    # ---- posterior of net tau on the probability scale ----
    post = idata.posterior
    A = post["alpha"].stack(s=("chain", "draw")).values.T      # S x NQ
    B = post["b"].stack(s=("chain", "draw")).values.T
    tau = expit(A + B) - expit(A) - cost
    out = dict(p_neg=(tau < 0).mean(0), tau_mean=tau.mean(0), tau_sd=tau.std(0),
               nu=float(post["nu"].mean()), sigma_u=float(post["sigma_u"].mean()),
               rhat_max=rhat_max, ess_min=ess_min, divergences=ndiv)

    # ---- posterior predictive for unseen candidates (expansion ranking) ----
    if cand_F is not None:
        rng = np.random.default_rng(seed)
        G = post["gamma"].stack(s=("chain", "draw")).values.T  # S x K
        Bt = post["beta"].stack(s=("chain", "draw")).values.T
        sa = post["sigma_a"].stack(s=("chain", "draw")).values
        su = post["sigma_u"].stack(s=("chain", "draw")).values
        nus = post["nu"].stack(s=("chain", "draw")).values
        S, NC = len(sa), len(cand_F)
        pos = np.zeros(NC); tot = np.zeros(NC)
        for s_i in range(S):                                   # stream to bound memory
            a_c = cand_F @ G[s_i] + sa[s_i] * rng.standard_normal(NC)
            b_c = cand_F @ Bt[s_i] + su[s_i] * rng.standard_t(max(nus[s_i], 2.05), NC)
            tc = expit(a_c + b_c) - expit(a_c) - cost
            pos += tc > 0; tot += tc
        out |= dict(cand_p_pos=pos / S, cand_mean=tot / S)
    return out


def demo(outlier_share, seed):
    W = make_world(outlier_share=outlier_share, seed=seed)
    print("PyMC fit ...")
    pmres = fit_pymc(W['n0'], W['c0'], W['n1'], W['c1'], W['F'], cand_F=W['FC'], seed=1)
    print("Gibbs cross-check ...")
    gb = fit_gibbs(W['n0'], W['c0'], W['n1'], W['c1'], W['F'], seed=11)
    eb = fit_eb(W['n0'], W['c0'], W['n1'], W['c1'], W['F'])
    netL, w = W['netL'], W['w']

    def stats(p_neg, name):
        rm = p_neg > 0.8
        fs = float((rm & (netL > 0)).sum() / max(rm.sum(), 1))
        val = float(np.sum(w * np.where(~rm, netL, 0)) * 1e5)
        print(f"{name:12s} removed {int(rm.sum()):4d}  false-share {fs:.3f}  value {val:.1f}")
        return rm

    rm_pm = stats(pmres['p_neg'], 'PyMC')
    rm_gb = stats(gb['p_neg'], 'Gibbs')
    stats(eb['p_neg'], 'EB')
    agree = float((rm_pm == rm_gb).mean())
    corr = float(np.corrcoef(pmres['p_neg'], gb['p_neg'])[0, 1])
    print(f"PyMC vs Gibbs: decision agreement {agree:.4f}, P(net<0) corr {corr:.4f}")
    print(f"PyMC nu {pmres['nu']:.1f} sigma_u {pmres['sigma_u']:.4f} | Gibbs nu {gb['nu']:.1f} sigma_u {gb['sigma_u']:.4f}")
    top = np.argsort(-pmres['cand_mean'])[:300]
    print(f"expansion top-300 truly positive: {float((W['net_cand'][top] > 0).mean()):.3f}")
    if agree < 0.95:
        print("WARNING: cross-check below 95% agreement — investigate before production use.")


def production(path, cost, linear):
    import csv
    rows = list(csv.DictReader(open(path)))
    ids = [r['query_id'] for r in rows]
    n0 = np.array([int(r['n0']) for r in rows]); c0 = np.array([int(r['c0']) for r in rows])
    n1 = np.array([int(r['n1']) for r in rows]); c1 = np.array([int(r['c1']) for r in rows])
    fk = [k for k in rows[0] if k.startswith('f')]
    X = np.array([[float(r[k]) for k in fk] for r in rows])
    F = X if linear else basis(X)
    res = fit_pymc(n0, c0, n1, c1, F, cost=cost)
    with open('posteriors_pymc.csv', 'w') as f:
        f.write("query_id,tau_mean,tau_sd,p_neg,action\n")
        for i, qid in enumerate(ids):
            act = ("probation" if res['p_neg'][i] > 0.8 else
                   "watch" if res['p_neg'][i] > 0.6 else "keep")
            f.write(f"{qid},{res['tau_mean'][i]:.5f},{res['tau_sd'][i]:.5f},{res['p_neg'][i]:.3f},{act}\n")
    print(f"wrote posteriors_pymc.csv (nu={res['nu']:.1f}, sigma_u={res['sigma_u']:.4f})")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--demo', action='store_true')
    ap.add_argument('--outliers', type=float, default=0.03)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--data'); ap.add_argument('--cost', type=float, default=COST)
    ap.add_argument('--linear', action='store_true')
    a = ap.parse_args()
    if a.demo: demo(a.outliers, a.seed)
    elif a.data: production(a.data, a.cost, a.linear)
    else: print(__doc__)
