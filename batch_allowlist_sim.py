"""
Batch allowlist iteration inside a standard user-level A/B.

World: 22,000 distinct queries with features phi(q) in R^6. True gross lift
Delta(q) = s(phi) + u_q (feature-driven signal + query idiosyncrasy).
Net effect = Delta - COST. Allowlist = top 2,000 queries by a noisy heuristic
on s(phi) — selected to be good, imperfectly. Traffic over allowlisted
queries is Zipf: the head query gets ~20k impressions/wk, the median gets
tens. 8-week A/B, users split 50/50; for each allowlisted query we observe
binomial conversions in each arm (control ~4.5%, treatment +Delta).

Estimators of per-query net effect:
  RAW   : difference in conversion rates (eligible if n>=30 per arm)
  RAW+T : raw, but act only if one-sided t <= -1.64
  EB    : empirical Bayes — weighted-ridge feature model f(phi) as prior mean,
          method-of-moments sigma_u, precision-weighted posterior per query
Decisions:
  prune q if (RAW: net<0) (RAW+T: net<0 & significant) (EB: P(net<0)>0.8)
Expansion (off-allowlist candidates, no outcome data by construction):
  add top-K by EB feature model vs K at random; scored against truth.
Metrics, median over SEEDS replications.
"""
import numpy as np, json

NQ_ALL = 22_000; NQ_LIST = 2_000; D = 6
COST = 0.002
WK_IMP = 150_000; WEEKS = 8
SEEDS = 40
K_ADD = 300
GRID = np.linspace(-0.06, 0.06, 121)  # net-effect grid (fraction), 0.1pp bins

def sfun(x):
    return 0.012*np.tanh(0.9*(x[:,0] + 0.8*x[:,1]*x[:,2] - 0.5*x[:,3]**2) + 0.3) + 0.003

def p0fun(x):
    return 1/(1+np.exp(-(-3.1 + 0.5*x[:,5] + 0.25*x[:,0])))

PAIRS = [(i,j) for i in range(D) for j in range(i+1,D)]
def phi(x):
    cols = [np.ones((len(x),1)), x, x**2] + [(x[:,i]*x[:,j])[:,None] for i,j in PAIRS]
    return np.hstack(cols)

def hist01(v, w=None):
    h,_ = np.histogram(np.clip(v, GRID[0], GRID[-1]), bins=GRID, weights=w)
    h = h.astype(float)
    return h/h.max() if h.max()>0 else h

def run(seed):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((NQ_ALL, D))
    s = sfun(x); u = rng.normal(0, 0.006, NQ_ALL)
    dlt = s + u                      # gross lift
    net = dlt - COST
    p0 = p0fun(x)
    h = s + rng.normal(0, 0.02, NQ_ALL)
    order = np.argsort(-h)
    L = order[:NQ_LIST]              # allowlist
    C = order[NQ_LIST:]              # candidates

    # Zipf traffic over the allowlist (rank by heuristic)
    w = (np.arange(NQ_LIST)+1.0)**-1.05
    w = w/w.sum()
    nq = np.round(w * WK_IMP * WEEKS).astype(int)
    n1 = rng.binomial(nq, 0.5); n0 = nq - n1
    pL0 = p0[L]; pL1 = np.clip(pL0 + dlt[L], 1e-4, 0.9)
    c1 = rng.binomial(n1, pL1); c0 = rng.binomial(n0, pL0)

    ok = (n0>=1)&(n1>=1)
    r1 = np.where(n1>0, c1/np.maximum(n1,1), 0.0)
    r0 = np.where(n0>0, c0/np.maximum(n0,1), 0.0)
    raw = r1 - r0                    # gross
    pp = (c0+c1+1)/(n0+n1+2)
    v = pp*(1-pp)*(1/np.maximum(n0,1)+1/np.maximum(n1,1))
    v[~ok] = np.inf

    netL = net[L]; wgt = w

    # --- feature model (weighted ridge), two IRLS-ish passes for sigma_u ---
    F = phi(x[L])
    sig2 = 0.004**2
    for _ in range(2):
        wt = 1.0/(v + sig2)
        G = (F*wt[:,None]).T @ F + 50.0*np.eye(F.shape[1])
        b = (F*wt[:,None]).T @ raw
        beta = np.linalg.solve(G, b)
        fhat = F @ beta
        # method of moments on well-measured queries:
        good = np.isfinite(v) & (v < 0.02**2)
        if np.any(good):
            estimate = np.average((raw[good] - fhat[good])**2 - v[good],
                                  weights=1 / v[good])
            if np.isfinite(estimate):
                sig2 = max(float(estimate), 1e-7)
    post_prec = 1/v + 1/sig2
    post = (raw/v + fhat/sig2)/post_prec
    post[~np.isfinite(v)] = fhat[~np.isfinite(v)]
    post_sd = np.sqrt(1/np.where(np.isfinite(v), post_prec, 1/sig2))

    # --- prune rules (on net effect) ---
    elig = (n0>=30)&(n1>=30)
    t = (raw - COST)/np.sqrt(v)
    rm_raw = elig & (raw - COST < 0)
    rm_rawt = elig & (t < -1.64)
    from scipy.stats import norm
    z = (0 - (post - COST))/post_sd
    p_neg = norm.cdf(z)
    rm_eb = p_neg > 0.8

    def prune_metrics(rm):
        n_rm = int(rm.sum())
        good_rm = int((rm & (netL>0)).sum())            # mistakes
        false_share = good_rm/n_rm if n_rm else 0.0
        keep = ~rm
        val = np.sum(wgt*np.where(keep, netL, 0.0))*1e5 # per 100k allowlisted imps
        return n_rm, false_share, val

    val_keepall = np.sum(wgt*netL)*1e5
    val_oracle  = np.sum(wgt*np.where(netL>0, netL, 0.0))*1e5
    m_raw, m_rawt, m_eb = prune_metrics(rm_raw), prune_metrics(rm_rawt), prune_metrics(rm_eb)

    # --- expansion: score candidates by feature model ---
    FC = phi(x[C]); fC = FC @ beta
    top = C[np.argsort(-(fC - COST))[:K_ADD]]
    rnd = rng.choice(C, K_ADD, replace=False)
    exp_model = float((net[top]>0).mean()), float(net[top].mean()*1e4)  # (share truly net-positive, mean net in pp*100)
    exp_rand  = float((net[rnd]>0).mean()), float(net[rnd].mean()*1e4)

    # --- densities (net effect, pp axis handled at render) ---
    d_true = hist01(netL)
    d_raw  = hist01((raw-COST)[elig])
    d_post = hist01(post-COST)
    clip_share = float(np.mean(np.abs((raw-COST)[elig]) > 0.06))

    # power stat: queries with n per arm enough to detect +1pp (80% power, alpha 5% two-sided)
    n_need = 2*(1.96+0.842)**2*0.045*0.955/(0.01**2)
    powered = float(np.mean(nq >= 2*n_need))
    med_n = float(np.median(nq))
    share_elig = float(elig.mean())

    return dict(m_raw=m_raw, m_rawt=m_rawt, m_eb=m_eb,
                val_keepall=val_keepall, val_oracle=val_oracle,
                exp_model=exp_model, exp_rand=exp_rand,
                d_true=d_true, d_raw=d_raw, d_post=d_post, clip_share=clip_share,
                powered=powered, med_n=med_n, share_elig=share_elig,
                share_neg_list=float((netL<0).mean()),
                traffic_neg=float(np.sum(wgt*(netL<0))))

res = [run(s) for s in range(SEEDS)]
def med(f): return float(np.median([f(r) for r in res]))
def medarr(k): return np.median([r[k] for r in res], axis=0)

def iqr(f): 
    a=[f(r) for r in res]; return [float(np.percentile(a,25)), float(np.percentile(a,75))]
out = dict(
 raw_iqr=iqr(lambda r: r['m_raw'][2]), rawt_iqr=iqr(lambda r: r['m_rawt'][2]), eb_iqr=iqr(lambda r: r['m_eb'][2]),
 raw_fs_iqr=iqr(lambda r: r['m_raw'][1]), rawt_fs_iqr=iqr(lambda r: r['m_rawt'][1]), eb_fs_iqr=iqr(lambda r: r['m_eb'][1]),
 expm_iqr=iqr(lambda r: r['exp_model'][0]),
 # prune: n removed, false share, value
 raw   = [med(lambda r: r['m_raw'][0]),  med(lambda r: r['m_raw'][1]),  med(lambda r: r['m_raw'][2])],
 rawt  = [med(lambda r: r['m_rawt'][0]), med(lambda r: r['m_rawt'][1]), med(lambda r: r['m_rawt'][2])],
 eb    = [med(lambda r: r['m_eb'][0]),   med(lambda r: r['m_eb'][1]),   med(lambda r: r['m_eb'][2])],
 keepall = med(lambda r: r['val_keepall']), oracle = med(lambda r: r['val_oracle']),
 exp_model = [med(lambda r: r['exp_model'][0]), med(lambda r: r['exp_model'][1])],
 exp_rand  = [med(lambda r: r['exp_rand'][0]),  med(lambda r: r['exp_rand'][1])],
 clip = med(lambda r: r['clip_share']), powered = med(lambda r: r['powered']),
 med_n = med(lambda r: r['med_n']), share_elig = med(lambda r: r['share_elig']),
 share_neg_list = med(lambda r: r['share_neg_list']),
 traffic_neg = med(lambda r: r['traffic_neg']),
)
# paired robustness
pair_eb_rawt=[r['m_eb'][2]-r['m_rawt'][2] for r in res]
pair_eb_keep=[r['m_eb'][2]-r['val_keepall'] for r in res]
pair_raw_keep=[r['m_raw'][2]-r['val_keepall'] for r in res]
print("EB beats gated-raw in", int(np.sum(np.array(pair_eb_rawt)>0)), "of", len(res), "runs; median diff", round(float(np.median(pair_eb_rawt)),1))
print("EB beats keep-all in", int(np.sum(np.array(pair_eb_keep)>0)), "runs; raw beats keep-all in", int(np.sum(np.array(pair_raw_keep)>0)), "runs")
import json as _j
dens=dict(true=medarr('d_true').tolist(), raw=medarr('d_raw').tolist(), post=medarr('d_post').tolist())
open('dens.json','w').write(_j.dumps(dens))
np.save('dens.npy', dict(true=medarr('d_true'), raw=medarr('d_raw'), post=medarr('d_post')), allow_pickle=True)
print(json.dumps({k:(np.round(v,4).tolist() if isinstance(v,list) else round(v,4)) for k,v in out.items()}, indent=1))
