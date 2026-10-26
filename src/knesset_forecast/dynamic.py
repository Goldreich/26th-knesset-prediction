"""Gaussian log-ratio state-space inference, integrating variance hyperparameters.

Rounded weighted percentages are measurements, never fabricated respondent counts.
Conditional Gaussian posteriors are exact; hyperparameter integration uses an
explicit discrete prior grid. This is a polling component, not a fundamentals model.
"""
from __future__ import annotations

from itertools import product
import numpy as np
from scipy import sparse
from scipy.linalg import helmert, solve_triangular
from scipy.sparse.linalg import splu
from scipy.special import logsumexp


def measurement_covariance(p: np.ndarray, reference: float, n: int) -> np.ndarray:
    """Delta-method ALR covariance with shared denominator and a reporting floor.

Design effect two, nominal n capped at 1500; .08 log-ratio reporting floor.
The fitted overdispersion multiplies this entire covariance.
"""
    if n <= 0 or reference <= 0 or np.any(p <= 0):
        raise ValueError("Positive reported proportions and sample size required")
    effective_n = min(n, 1500) / 2
    return np.diag(1 / (effective_n*p) + .08**2) + np.ones((len(p), len(p)))/(effective_n*reference)


def design(observations: list[dict], *, keys: list[str], days: int,
           breaks: list[int] = (), initial_mean: np.ndarray | None = None) -> dict:
    """Missing categories remain missing; house effects sum to zero by construction."""
    k = len(keys)
    firms = sorted({o['firm'] for o in observations})
    if not observations or len(firms) < 2 or days < 2:
        raise ValueError("Repeated observations from at least two firms required")
    h = helmert(len(firms), full=False).T
    size = days*k + (len(firms)-1)*k
    blocks, values = [], []
    for o in observations:
        js = [keys.index(key) for key in o['keys']]
        a = np.zeros((len(js), size))
        for r, j in enumerate(js):
            a[r, o['day']*k+j] = 1
            for f, coef in enumerate(h[firms.index(o['firm'])]):
                a[r, days*k+f*k+j] = coef
            if o.get('reference_key'):
                reference=keys.index(o['reference_key'])
                a[r,o['day']*k+reference]-=1
                for f,coef in enumerate(h[firms.index(o['firm'])]):
                    a[r,days*k+f*k+reference]-=coef
        chol = np.linalg.cholesky(o['covariance'])
        blocks.append(sparse.csr_matrix(solve_triangular(chol, a, lower=True)))
        values.append(solve_triangular(chol, o['y'], lower=True))
    a = sparse.vstack(blocks, format='csc')
    y = np.concatenate(values)
    # Isotropic centered log-coordinate innovations induce correlated ALR changes.
    c = np.eye(k)+np.ones((k, k))
    w = np.linalg.inv(np.linalg.cholesky(c))
    step = sparse.diags([-np.ones(days-1), np.ones(days-1)], [0, 1], shape=(days-1, days))
    multipliers = np.ones(days-1)
    for b in breaks:
        if 0 < b < days:
            multipliers[b-1] = 5  # SD multiplier at an explicit lineup discontinuity
    step = sparse.diags(1/multipliers) @ step
    rw = sparse.hstack([sparse.kron(step, w), sparse.csr_matrix(((days-1)*k, (len(firms)-1)*k))], format='csc')
    initial = sparse.hstack([sparse.csc_matrix(w/3), sparse.csr_matrix((k, size-k))], format='csc')
    house = sparse.hstack([sparse.csr_matrix(((len(firms)-1)*k, days*k)),
                           sparse.kron(sparse.eye(len(firms)-1), w)], format='csc')
    mean = np.full(k, -1.2) if initial_mean is None else np.asarray(initial_mean)
    return dict(a=a, y=y, rw=rw, initial=initial, initial_y=w@mean/3,
                house=house, days=days, keys=keys, firms=firms, helmert=h,
                size=size, k=k, observation_count=len(observations))


def fit(model: dict, *, q_grid=(.006, .012, .024, .048, .096),
        h_grid=(.03, .06, .12, .24, .48), s_grid=(.5, .75, 1.125, 1.6875, 2.53125),
        n_draws=4000, seed=26024) -> dict:
    """Integrate a declared finite prior, then sample independent Gaussian draws.

Lognormal grid prior medians: q=.024/day, h=.12, s=1, log-SD=.8.
No MCMC convergence claims: numerical checks concern solves and grid sensitivity.
"""
    a, y, rw, initial, house = (model[key] for key in ('a','y','rw','initial','house'))
    aa, rr, ii, hh = (b.T@b for b in (a, rw, initial, house))
    ay, iy = a.T@y, initial.T@model['initial_y']
    grid, logs = [], []
    for q, h, s in product(q_grid, h_grid, s_grid):
        precision = (aa/s**2+rr/q**2+ii+hh/h**2).tocsc()
        factor = splu(precision)
        rhs = ay/s**2+iy
        mean = factor.solve(rhs)
        logdet = np.log(np.abs(factor.U.diagonal())).sum()
        # The proper initial prior is fixed. RW and house prior normalizers matter.
        loglike = -.5*(len(y)*np.log(s**2)+rw.shape[0]*np.log(q**2)+house.shape[0]*np.log(h**2)
                       + logdet + y@y/s**2 + model['initial_y']@model['initial_y'] - rhs@mean)
        logprior = -.5*sum((np.log(v/m)/.8)**2 for v, m in zip((q,h,s),(.024,.12,1)))
        grid.append((q,h,s)); logs.append(loglike+logprior)
    weights = np.exp(np.array(logs)-logsumexp(logs))
    rng = np.random.default_rng(seed)
    assignments = rng.choice(len(grid), n_draws, p=weights)
    draws = np.empty((n_draws, model['size']))
    max_residual = 0.
    for index in np.unique(assignments):
        q,h,s = grid[index]
        ids = np.flatnonzero(assignments == index)
        precision = (aa/s**2+rr/q**2+ii+hh/h**2).tocsc()
        factor = splu(precision)
        rhs = ay/s**2+iy
        mean = factor.solve(rhs)
        max_residual = max(max_residual, float(np.max(np.abs(precision@mean-rhs)) / max(1, np.max(np.abs(rhs)))))
        # Perturb-and-solve: noise covariance is exactly the precision matrix.
        for start in range(0,len(ids),100):
            subset=ids[start:start+100]; n=len(subset)
            noise=(a.T@rng.normal(size=(a.shape[0],n))/s
                   +rw.T@rng.normal(size=(rw.shape[0],n))/q
                   +house.T@rng.normal(size=(house.shape[0],n))/h
                   +initial.T@rng.normal(size=(initial.shape[0],n)))
            draws[subset]=(mean[:,None]+factor.solve(noise)).T
    grid_array=np.asarray(grid)
    marginals={name:[{'value':float(v),'probability':float(weights[grid_array[:,j]==v].sum())} for v in sorted(set(grid_array[:,j]))]
               for j,name in enumerate(('daily_movement_sd','house_effect_sd','measurement_multiplier'))}
    edge={name:rows[0]['probability']+rows[-1]['probability'] for name,rows in marginals.items()}
    k,days=model['k'],model['days']
    effects=draws[:,days*k:].reshape(n_draws,-1,k)
    effects=np.einsum('fh,nhk->nfk',model['helmert'],effects)
    return dict(state_draws=draws[:,:days*k].reshape(n_draws,days,k), house_draws=effects,
                grid=[dict(q=q,h=h,s=s,probability=float(w)) for (q,h,s),w in zip(grid,weights)],
                diagnostics={'algorithm':'finite-grid integrated Gaussian posterior; independent conditional draws',
                             'max_relative_solve_residual':max_residual,'hyperparameter_marginals':marginals,
                             'grid_boundary_probability':edge,'observations':model['observation_count'],
                             'scalar_measurements':len(y),'latent_parameters':model['size'],
                             'n_draws':n_draws,'seed':seed})
