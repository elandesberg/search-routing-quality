"""
Hierarchical Bayesian allowlist estimator — reference implementation.

THE MODEL (logit scale, full uncertainty propagation, heavy-tailed effects)

  c0_q ~ Binomial(n0_q, sigmoid(alpha_q))                    control arm
  c1_q ~ Binomial(n1_q, sigmoid(alpha_q + b_q))              treatment arm
  alpha_q ~ Normal( Phi_q @ gamma, sigma_a^2 )               pooled baselines
  b_q     =  Phi_q @ beta + u_q                              pooled effects
  u_q     ~ Student-t( nu, 0, sigma_u )                      heavy tails: a query
                                                             may truly differ from
                                                             its type
  gamma, beta ~ Normal(0, 1);  sigma_a^2, sigma_u^2 ~ InvGamma(2, .02);
  nu ~ discrete uniform on {2,3,4,6,8,12,20,50}

Why this upgrades the two-stage EB fit in batch_allowlist_sim.py:
  * binomial likelihood on the logit scale (no rate-difference approximation)
  * uncertainty in beta/gamma/sigma_u propagated into every posterior, so
    P(net<0) is calibrated where the prior does the work (the tail)
  * t tails let a genuinely deviant query override its type's prior instead of
    being shrunk into invisibility

SAMPLER: Metropolis-within-Gibbs, exploiting the scale-mixture trick
  u_q | lambda_q ~ N(0, sigma_u^2/lambda_q),  lambda_q ~ Gamma(nu/2, nu/2)
so gamma, beta, sigma_a^2, sigma_u^2, lambda are conjugate Gibbs updates and
only (alpha_q, b_q) need Metropolis — vectorized across queries (each query's
2-D block is conditionally independent given hyperparameters), with per-query
adaptive step sizes during burn-in. Port to Stan/PyMC/numpyro where available;
this file is also the model spec.

USAGE
  demo mode (synthetic world, EB-vs-Bayes comparison, outlier stress test):
      python3 hier_bayes_allowlist.py --demo
  production mode:
      python3 hier_bayes_allowlist.py --data logs.csv --cost 0.002
  logs.csv columns: query_id, n0, c0, n1, c1, f1..fK  (raw features; a
  quadratic+interaction basis is built unless --linear). Outputs
  posteriors.csv with mean/sd of net tau, P(net<0), and suggested action.
"""
import numpy as np, json, argparse, time
from scipy.special import gammaln, expit

COST = 0.002
NU_GRID = np.array([2, 3, 4, 6, 8, 12, 20, 50])

def basis(x):
    d = x.shape[1]
    cols = [np.ones((len(x), 1)), x, x**2]
    cols += [(x[:, i] * x[:, j])[:, None] for i in range(d) for j in range(i + 1, d)]
    return np.hstack(cols)

# ---------------------------------------------------------------- sampler ----
def fit(n0, c0, n1, c1, F, sweeps=3500, burn=1500, thin=2, seed=0,
        cand_F=None, cost=COST, progress=False):
    rng = np.random.default_rng(seed)
    NQ, K = F.shape
    # init
    a = np.log((c0 + 1) / (n0 - c0 + 1.0))            # logit baseline
    b = np.zeros(NQ)
    gam = np.zeros(K); bet = np.zeros(K)
    s2a, s2u, nu = 1.0, 0.05**2, 8.0
    lam = np.ones(NQ)
    step_a = np.full(NQ, 0.3); step_b = np.full(NQ, 0.4)
    FtF = F.T @ F
    prior_prec = 1.0  # N(0,1) on gamma, beta

    def loglik(a_, b_):
        e0 = np.clip(a_, -12, 6); e1 = np.clip(a_ + b_, -12, 6)
        return (c0 * e0 - n0 * np.log1p(np.exp(e0))
              + c1 * e1 - n1 * np.log1p(np.exp(e1)))

    keep_ct = 0
    p_neg = np.zeros(NQ); tau_sum = np.zeros(NQ); tau_sq = np.zeros(NQ)
    if cand_F is not None:
        NC = len(cand_F)
        cand_pos = np.zeros(NC); cand_sum = np.zeros(NC)

    ll = loglik(a, b)
    t0 = time.time()
    for it in range(sweeps):
        # --- alpha_q Metropolis (vectorized) ---
        ma = F @ gam
        prop = a + step_a * rng.standard_normal(NQ)
        ll_p = loglik(prop, b)
        logr = ll_p - ll - (prop - ma)**2/(2*s2a) + (a - ma)**2/(2*s2a)
        acc = np.log(rng.random(NQ)) < logr
        a = np.where(acc, prop, a); ll = np.where(acc, ll_p, ll)
        if it < burn: step_a *= np.exp(0.02 * (acc - 0.44))
        # --- b_q Metropolis (vectorized) ---
        mb = F @ bet; pv = s2u / lam
        prop = b + step_b * rng.standard_normal(NQ)
        ll_p = loglik(a, prop)
        logr = ll_p - ll - (prop - mb)**2/(2*pv) + (b - mb)**2/(2*pv)
        acc = np.log(rng.random(NQ)) < logr
        b = np.where(acc, prop, b); ll = np.where(acc, ll_p, ll)
        if it < burn: step_b *= np.exp(0.02 * (acc - 0.44))
        # --- gamma | alpha (conjugate) ---
        A = FtF / s2a + prior_prec * np.eye(K)
        gam = np.linalg.solve(A, F.T @ a / s2a)
        gam += np.linalg.cholesky(np.linalg.inv(A)) @ rng.standard_normal(K)
        # --- sigma_a^2 | residuals (conjugate IG) ---
        r = a - F @ gam
        s2a = 1/rng.gamma(2 + NQ/2, 1/(0.02 + 0.5*np.sum(r**2)))
        # --- beta | b, lambda (weighted conjugate) ---
        w = lam / s2u
        A = (F * w[:, None]).T @ F + prior_prec * np.eye(K)
        bet = np.linalg.solve(A, (F * w[:, None]).T @ b)
        bet += np.linalg.cholesky(np.linalg.inv(A)) @ rng.standard_normal(K)
        # --- u, sigma_u^2, lambda, nu ---
        u = b - F @ bet
        s2u = 1/rng.gamma(2 + NQ/2, 1/(0.02 + 0.5*np.sum(lam * u**2)))
        lam = rng.gamma((nu + 1)/2, 2/(nu + u**2/s2u))
        # griddy Gibbs for nu
        lg = (NU_GRID[:, None]/2*np.log(NU_GRID[:, None]/2) - gammaln(NU_GRID[:, None]/2)
              + (NU_GRID[:, None]/2 - 1)*np.log(lam)[None, :] - NU_GRID[:, None]/2*lam[None, :])
        lp = lg.sum(1); lp -= lp.max()
        nu = rng.choice(NU_GRID, p=np.exp(lp)/np.exp(lp).sum())
        # --- collect ---
        if it >= burn and (it - burn) % thin == 0:
            keep_ct += 1
            tau = expit(a + b) - expit(a) - cost
            p_neg += (tau < 0); tau_sum += tau; tau_sq += tau**2
            if cand_F is not None:
                a_c = cand_F @ gam + np.sqrt(s2a)*rng.standard_normal(NC)
                lam_c = rng.gamma(nu/2, 2/nu, NC)
                b_c = cand_F @ bet + np.sqrt(s2u/lam_c)*rng.standard_normal(NC)
                tc = expit(a_c + b_c) - expit(a_c) - cost
                cand_pos += (tc > 0); cand_sum += tc
        if progress and it % 500 == 0:
            print(f"  sweep {it}/{sweeps}  nu={nu}  sigma_u={np.sqrt(s2u):.4f}  {time.time()-t0:.0f}s")

    out = dict(p_neg=p_neg/keep_ct, tau_mean=tau_sum/keep_ct,
               tau_sd=np.sqrt(np.maximum(tau_sq/keep_ct - (tau_sum/keep_ct)**2, 0)),
               nu=float(nu), sigma_u=float(np.sqrt(s2u)), draws=keep_ct)
    if cand_F is not None:
        out |= dict(cand_p_pos=cand_pos/keep_ct, cand_mean=cand_sum/keep_ct)
    return out

# --------------------------------------------- EB with t tails (workhorse) ---
def fit_eb_t(n0, c0, n1, c1, F, cost=COST, nu=4.0, iters=6):
    """Two-stage EB with Student-t tails via robust IRLS (approximate EM).

    RECORDED NEGATIVE RESULT — kept for reference, NOT recommended. On the
    --demo outlier world this approximation catches FEWER true outliers than
    plain Gaussian EB (0.32 vs 0.36) at roughly double the false-removal share
    (0.195 vs 0.084). Reason: it downweights on the standardized residual
    (raw - fhat)^2/(v + sigma_u^2), which cannot tell a genuinely deviant query
    from a noisily measured one — v-dominated deviations get flagged as
    outliers too. The full MCMC avoids this because lambda_q is inferred
    jointly with b_q under the binomial likelihood. Conclusion: use fit_eb for
    the cheap pass and fit() for the outlier-aware pass; there is no useful
    middle rung."""
    ok = (n0 >= 1) & (n1 >= 1)
    r1 = np.where(n1 > 0, c1/np.maximum(n1, 1), 0); r0 = np.where(n0 > 0, c0/np.maximum(n0, 1), 0)
    raw = r1 - r0
    pp = (c0 + c1 + 1)/(n0 + n1 + 2)
    v = pp*(1 - pp)*(1/np.maximum(n0, 1) + 1/np.maximum(n1, 1)); v[~ok] = np.inf
    sig2 = 0.004**2; w = np.ones(len(raw)); fh = np.zeros(len(raw))
    for _ in range(iters):
        wt = w/(v + sig2)
        A = (F*wt[:, None]).T @ F + 50*np.eye(F.shape[1])
        beta = np.linalg.solve(A, (F*wt[:, None]).T @ raw)
        fh = F @ beta
        r2 = (raw - fh)**2/(v + sig2)          # standardized residual^2
        w = np.where(np.isfinite(v), (nu + 1)/(nu + r2), 1.0)
        good = np.isfinite(v) & (v < 0.02**2)
        sig2 = max(np.average(((raw-fh)**2 - v)[good], weights=(w/v)[good]), 1e-7)
    pv = sig2/np.clip(w, 0.05, None)            # per-query effective prior var
    prec = 1/v + 1/pv
    post = (raw/v + fh/pv)/prec; post[~np.isfinite(v)] = fh[~np.isfinite(v)]
    sd = np.sqrt(1/np.where(np.isfinite(v), prec, 1/(sig2/1.0)))
    from scipy.stats import norm
    return dict(p_neg=norm.cdf((0 - (post - cost))/sd), tau_mean=post - cost, beta=beta)

# ------------------------------------------------------- EB two-stage (ref) --
def fit_eb(n0, c0, n1, c1, F, cost=COST):
    ok = (n0 >= 1) & (n1 >= 1)
    r1 = np.where(n1 > 0, c1/np.maximum(n1, 1), 0); r0 = np.where(n0 > 0, c0/np.maximum(n0, 1), 0)
    raw = r1 - r0
    pp = (c0 + c1 + 1)/(n0 + n1 + 2)
    v = pp*(1 - pp)*(1/np.maximum(n0, 1) + 1/np.maximum(n1, 1)); v[~ok] = np.inf
    sig2 = 0.004**2
    for _ in range(2):
        wt = 1/(v + sig2)
        A = (F*wt[:, None]).T @ F + 50*np.eye(F.shape[1])
        beta = np.linalg.solve(A, (F*wt[:, None]).T @ raw)
        fh = F @ beta
        good = np.isfinite(v) & (v < 0.02**2)
        sig2 = max(np.average((raw[good]-fh[good])**2 - v[good], weights=1/v[good]), 1e-7)
    prec = 1/v + 1/sig2
    post = (raw/v + fh/sig2)/prec; post[~np.isfinite(v)] = fh[~np.isfinite(v)]
    sd = np.sqrt(1/np.where(np.isfinite(v), prec, 1/sig2))
    from scipy.stats import norm
    return dict(p_neg=norm.cdf((0 - (post - cost))/sd), tau_mean=post - cost, beta=beta)

# ------------------------------------------------------------------ demo -----
def make_world(outlier_share=0.03, seed=0):
    """Shared synthetic world (same as batch_allowlist_sim.py): returns the
    logged A/B data for the allowlist plus ground truth for scoring."""
    rng = np.random.default_rng(seed)
    NQ_ALL, NQ_LIST, D = 22_000, 2_000, 6
    x = rng.standard_normal((NQ_ALL, D))
    s = 0.012*np.tanh(0.9*(x[:,0] + 0.8*x[:,1]*x[:,2] - 0.5*x[:,3]**2) + 0.3) + 0.003
    u = rng.normal(0, 0.006, NQ_ALL)
    dlt = s + u
    # outliers: genuinely bad queries hidden among good-looking types
    out_mask = rng.random(NQ_ALL) < outlier_share
    dlt = np.where(out_mask, dlt - 0.025, dlt)
    net = dlt - COST
    p0 = expit(-3.1 + 0.5*x[:,5] + 0.25*x[:,0])
    h = s + rng.normal(0, 0.02, NQ_ALL)
    L = np.argsort(-h)[:NQ_LIST]; C = np.argsort(-h)[NQ_LIST:]
    w = (np.arange(NQ_LIST)+1.0)**-1.05; w /= w.sum()
    nq = np.round(w*150_000*8).astype(int)
    n1 = rng.binomial(nq, 0.5); n0 = nq - n1
    p1 = np.clip(p0[L] + dlt[L], 1e-4, 0.6)
    c1 = rng.binomial(n1, p1); c0 = rng.binomial(n0, p0[L])
    return dict(n0=n0, c0=c0, n1=n1, c1=c1, F=basis(x[L]), FC=basis(x[C[:20_000]]),
                netL=net[L], net_cand=net[C[:20_000]], outL=out_mask[L], w=w, nq=nq)

def demo(outlier_share=0.03, seed=0):
    W = make_world(outlier_share, seed)
    n0, c0, n1, c1, F, FC = W['n0'], W['c0'], W['n1'], W['c1'], W['F'], W['FC']

    print("fitting EB two-stage ...")
    eb = fit_eb(n0, c0, n1, c1, F)
    ebt = fit_eb_t(n0, c0, n1, c1, F)
    print("fitting hierarchical Bayes (chain 1) ...")
    hb = fit(n0, c0, n1, c1, F, seed=11, cand_F=FC, progress=True)
    print("fitting hierarchical Bayes (chain 2, agreement check) ...")
    hb2 = fit(n0, c0, n1, c1, F, seed=77)

    netL = W['netL']; outL = W['outL']; w = W['w']; nq = W['nq']
    net_cand = W['net_cand']
    agree = float(np.mean((hb['p_neg'] > 0.8) == (hb2['p_neg'] > 0.8)))
    corr = float(np.corrcoef(hb['p_neg'], hb2['p_neg'])[0, 1])

    def prune_stats(pn, name):
        rm = pn > 0.8
        n_rm = int(rm.sum()); mistakes = float((rm & (netL > 0)).mean()*n_rm/n_rm) if n_rm else 0
        fs = float((rm & (netL > 0)).sum()/n_rm) if n_rm else 0.0
        val = float(np.sum(w*np.where(~rm, netL, 0))*1e5)
        # outlier catch: true outlier-negatives with enough traffic to be catchable at all
        catchable = outL & (netL < 0) & (nq >= 200)
        caught = float((rm & catchable).sum()/max(catchable.sum(), 1))
        return dict(rule=name, removed=n_rm, false_share=round(fs, 3), value=round(val, 1),
                    outlier_catch=round(caught, 3))

    def calib(pn, name):
        rows = []
        for lo, hi in [(0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]:
            m = (pn >= lo) & (pn < hi)
            rows.append(dict(bin=f"{lo}-{hi}", n=int(m.sum()),
                             actual_neg=round(float((netL[m] < 0).mean()), 3) if m.sum() else None))
        return {name: rows}

    keepall = float(np.sum(w*netL)*1e5)
    oracle = float(np.sum(w*np.where(netL > 0, netL, 0))*1e5)
    res = dict(world=dict(keepall=round(keepall,1), oracle=round(oracle,1),
                          share_neg=round(float((netL<0).mean()),3),
                          outliers_on_list=int(outL.sum())),
               chains=dict(decision_agreement=round(agree,4), p_neg_corr=round(corr,4),
                           nu_posterior=hb['nu'], sigma_u=round(hb['sigma_u'],4)),
               prune=[prune_stats(eb['p_neg'], 'EB-gaussian'), prune_stats(ebt['p_neg'], 'EB-t-IRLS'),
                      prune_stats(hb['p_neg'], 'Bayes-t')],
               calibration=[calib(eb['p_neg'], 'EB'), calib(ebt['p_neg'], 'EB-t'), calib(hb['p_neg'], 'Bayes')],
               expansion=dict(
                   top300_share_pos=round(float((net_cand[np.argsort(-hb['cand_mean'])[:300]] > 0).mean()),3),
                   top300_mean_pp=round(float(net_cand[np.argsort(-hb['cand_mean'])[:300]].mean()*100),3)))
    print(json.dumps(res, indent=1, default=str))
    return res

# ------------------------------------------------------------- production ----
def production(path, cost, linear):
    import csv
    rows = list(csv.DictReader(open(path)))
    ids = [r['query_id'] for r in rows]
    n0 = np.array([int(r['n0']) for r in rows]); c0 = np.array([int(r['c0']) for r in rows])
    n1 = np.array([int(r['n1']) for r in rows]); c1 = np.array([int(r['c1']) for r in rows])
    fk = [k for k in rows[0] if k.startswith('f')]
    X = np.array([[float(r[k]) for k in fk] for r in rows])
    F = X if linear else basis(X)
    hb = fit(n0, c0, n1, c1, F, cost=cost, progress=True)
    with open('posteriors.csv', 'w') as f:
        f.write("query_id,tau_mean,tau_sd,p_neg,action\n")
        for i, qid in enumerate(ids):
            act = ("probation" if hb['p_neg'][i] > 0.8 else
                   "watch" if hb['p_neg'][i] > 0.6 else "keep")
            f.write(f"{qid},{hb['tau_mean'][i]:.5f},{hb['tau_sd'][i]:.5f},{hb['p_neg'][i]:.3f},{act}\n")
    print(f"wrote posteriors.csv  (nu={hb['nu']}, sigma_u={hb['sigma_u']:.4f}, draws={hb['draws']})")

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--demo', action='store_true')
    ap.add_argument('--outliers', type=float, default=0.03)
    ap.add_argument('--data'); ap.add_argument('--cost', type=float, default=COST)
    ap.add_argument('--linear', action='store_true')
    a = ap.parse_args()
    if a.demo: demo(outlier_share=a.outliers)
    elif a.data: production(a.data, a.cost, a.linear)
    else: print(__doc__)
