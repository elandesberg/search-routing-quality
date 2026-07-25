"""
Toy world for the routing-exploration argument. Truth is known, so policies
can be scored exactly.

World: search sessions with features x (8 dims; two are "nuisance" dims the
heuristic partly keyed on). Baseline conversion p0(x) ~ 4%. Enhanced path
shifts conversion by delta(x), which can be negative. Serving cost in
conversion units: COST per enhanced impression. Net effect tau(x)=delta-COST.

Status quo: allowlist A = top 5% of a deterministic heuristic score h(x)
correlated with BOTH tau (selection on the outcome) and p0 (composition).

Designs compared at EQUAL exploration budget (same expected enhanced volume):
  broad : uncertainty set = wide slice (h in P10..P95), epsilon = 2%
  narrow: uncertainty set = thin slice just under the cutoff (P90..P95),
          epsilon scaled up to match budget (~34%)
Both keep a 10% holdback on the allowlist itself (e = 0.90 there).

Learner: T-learner, IPW weighted least squares on phi(x)=[1, x, x^2, x_i x_j]
(deliberately imperfect: true delta uses tanh of an interaction-heavy latent).
Policy: route iff tau_hat(x) > 0. Value = E[pi * tau] per 100k sessions,
computed on a fresh evaluation draw with the TRUE tau.
"""
import numpy as np, json, time

D = 8
COST = 0.002
WEEKLY = 1_500_000
WEEKS = 8
HOLDBACK = 0.10
SEEDS = 24
LAM = 3.0  # ridge

def draw(rng, n): return rng.standard_normal((n, D))

def g(x):   return x[:,0] + 0.9*x[:,1]*x[:,2] - 0.55*x[:,3]**2 + 0.5*x[:,4] + 0.3
def p0(x):
    z = -3.15 + 0.55*x[:,0] - 0.25*x[:,3] + 0.25*x[:,5]
    return 1/(1+np.exp(-z))
def delta(x): return 0.028*np.tanh(0.8*g(x) - 0.35) - 0.004
def tau(x):   return delta(x) - COST
def heur(x):  return g(x) + 0.9*x[:,0] + 1.1*x[:,6]   # deterministic; x6 = junk the heuristic keyed on

PAIRS = [(i,j) for i in range(D) for j in range(i+1,D)]
def phi(x):
    cols = [np.ones((len(x),1)), x, x**2]
    cols += [(x[:,i]*x[:,j])[:,None] for i,j in PAIRS]
    return np.hstack(cols)  # 1+8+8+28 = 45

def outcomes(x, W, rng):
    p = np.clip(p0(x) + W*delta(x), 1e-4, 0.6)
    return (rng.random(len(x)) < p).astype(np.int8)

class WLS:
    def __init__(self, k): self.G = LAM*np.eye(k); self.b = np.zeros(k)
    def update(self, F, y, w):
        Fw = F * w[:,None]
        self.G += Fw.T @ F; self.b += Fw.T @ y
    def coef(self): return np.linalg.solve(self.G, self.b)

def run_seed(seed):
    rng = np.random.default_rng(seed)
    xc = draw(rng, 300_000)                    # evaluation draw
    hc = heur(xc)
    h_cut, h_low, h_nar = np.quantile(hc, [0.95, 0.10, 0.90])
    Fh = phi(xc); tau_c = tau(xc)

    A_c = hc >= h_cut
    v0    = float(np.mean(np.where(A_c, tau_c, 0)) * 1e5)
    vstar = float(np.mean(np.where(tau_c > 0, tau_c, 0)) * 1e5)
    att   = float(delta(xc[A_c]).mean())
    share_pos = float((tau_c > 0).mean())

    # status-quo logs: naive contrast
    xw = draw(rng, WEEKLY); hw = heur(xw)
    W = (hw >= h_cut).astype(np.int8)
    Y = outcomes(xw, W, rng)
    naive = float(Y[W==1].mean() - Y[W==0].mean())
    base  = float(Y[W==0].mean())

    p_br = 0.85; eps_br = 0.02
    p_na = 0.05; eps_na = eps_br * p_br / p_na

    def run_design(lo, hi, eps):
        # support = where the design actually collects both arms: U ∪ A
        sup_c = ((hc >= lo) & (hc < h_cut)) | A_c
        vstar_sup = float(np.mean(np.where(sup_c & (tau_c > 0), tau_c, 0)) * 1e5)
        m1, m0 = WLS(45), WLS(45)
        vals, vals_unr = [], []
        for wk in range(WEEKS):
            x = draw(rng, WEEKLY); h = heur(x)
            e = np.zeros(len(x))
            e[h >= h_cut] = 1 - HOLDBACK
            inU = (h >= lo) & (h < hi)
            e[inU] = eps
            Wv = (rng.random(len(x)) < e).astype(np.int8)
            keep = e > 0
            tr = keep & (Wv==1); ct = keep & (Wv==0)
            # cap logged rows for speed: all treated in U, subsample A-treated & controls
            idx_trU = np.flatnonzero(tr & inU)
            idx_trA = np.flatnonzero(tr & ~inU)
            idx_trA = rng.choice(idx_trA, size=min(len(idx_trA), 6000), replace=False)
            n_tr = len(idx_trU) + len(idx_trA)
            idx_ct = np.flatnonzero(ct)
            idx_ct = rng.choice(idx_ct, size=min(len(idx_ct), 2*n_tr), replace=False)
            Yv = outcomes(x, Wv, rng)
            idx_t = np.concatenate([idx_trU, idx_trA])
            m1.update(phi(x[idx_t]), Yv[idx_t].astype(float), 1/np.clip(e[idx_t],1e-3,1))
            m0.update(phi(x[idx_ct]), Yv[idx_ct].astype(float), 1/np.clip(1-e[idx_ct],1e-3,1))
            tau_hat = Fh @ m1.coef() - Fh @ m0.coef() - COST
            route = tau_hat > 0
            vals.append(float(np.mean(np.where(route & sup_c, tau_c, 0)) * 1e5))
            vals_unr.append(float(np.mean(np.where(route, tau_c, 0)) * 1e5))
        return vals, vals_unr, vstar_sup

    v_br, v_br_unr, vs_br = run_design(h_low, h_cut, eps_br)
    v_na, v_na_unr, vs_na = run_design(h_nar, h_cut, eps_na)
    return dict(naive=naive, base=base, att=att, v0=v0, vstar=vstar,
                share_pos=share_pos, eps_na=eps_na,
                v_br=v_br, v_na=v_na, v_br_unr=v_br_unr, v_na_unr=v_na_unr,
                vs_br=vs_br, vs_na=vs_na)

t0 = time.time()
res = [run_seed(s) for s in range(SEEDS)]
def med(k):  return float(np.median([r[k] for r in res]))
def medv(k): return np.round(np.median([r[k] for r in res], axis=0), 1).tolist()
def qv(k,p): return np.round(np.percentile([r[k] for r in res], p, axis=0), 1).tolist()
out = dict(naive=med('naive'), base=med('base'), att=med('att'),
           v0=round(med('v0'),1), vstar=round(med('vstar'),1),
           vs_br=round(med('vs_br'),1), vs_na=round(med('vs_na'),1),
           share_pos=med('share_pos'), eps_na=med('eps_na'),
           br=medv('v_br'), br25=qv('v_br',25), br75=qv('v_br',75),
           na=medv('v_na'), na25=qv('v_na',25), na75=qv('v_na',75),
           br_unr=medv('v_br_unr'), na_unr=medv('v_na_unr'),
           secs=round(time.time()-t0,1))
print(json.dumps(out, indent=1))
