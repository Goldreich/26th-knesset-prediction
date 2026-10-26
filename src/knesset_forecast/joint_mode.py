"""Predictive sampling and exact-parliament cell probability integration."""
from __future__ import annotations
import numpy as np
from scipy.special import logsumexp,ndtr,ndtri,roots_genlaguerre,gammaln,softmax
from scipy.stats import qmc

def sample_votes(posterior: dict, n: int, rng) -> np.ndarray:
    """Independent fresh predictive draws, not resampling the 4,000 issued draws."""
    weights=posterior['weights']; groups=rng.choice(len(weights),n,p=weights)
    z=np.empty((n,len(posterior['keys'])-1))
    for g in np.unique(groups):
        rows=np.flatnonzero(groups==g)
        z[rows]=rng.normal(size=(len(rows),z.shape[1]))@np.linalg.cholesky(posterior['covariances'][g]).T+posterior['means'][g]
    sd=np.sqrt(posterior['error_scale']/rng.gamma(posterior['error_shape'],size=n))
    logits=np.column_stack([np.zeros(n),z])+rng.normal(size=(n,z.shape[1]+1))*sd[:,None]
    return softmax(logits,axis=1)*(1-posterior['residual_mass'])

def allocate_batch(votes: np.ndarray, pairs: list[tuple[int,int]], *, threshold=.0325, total_seats=120) -> np.ndarray:
    """Vectorized continuous-share version, verified against the rational engine.

Inputs omit only fixed subthreshold minor categories; the threshold denominator
is still ALL valid votes, i.e. one. This is never used for integer official votes.
"""
    votes=np.asarray(votes,float); n,k=votes.shape
    passed=votes>=threshold
    v=np.where(passed,votes,0.)
    eligible=v.sum(axis=1)
    if np.any(eligible<=0):raise ValueError('No qualified list')
    initial=np.floor(v/eligible[:,None]*total_seats).astype(np.int16)
    gv=np.column_stack([v,np.zeros((n,len(pairs)))])
    gs=np.column_stack([initial,np.zeros((n,len(pairs)),dtype=np.int16)])
    both=[]
    for g,(x,y) in enumerate(pairs):
        mask=passed[:,x]&passed[:,y];both.append(mask)
        gv[mask,k+g]=v[mask,x]+v[mask,y];gs[mask,k+g]=initial[mask,x]+initial[mask,y]
        gv[mask,x]=0;gv[mask,y]=0;gs[mask,x]=0;gs[mask,y]=0
    left=total_seats-gs.sum(axis=1); rows=np.arange(n)
    while left.max(initial=0)>0:
        quot=gv/(gs+1)
        quot[(2*gs>=total_seats)&(2*gv<=eligible[:,None])]=-1
        winner=np.argmax(quot,axis=1);pending=left>0
        gs[rows[pending],winner[pending]]+=1;left[pending]-=1
    out=gs[:,:k].copy()
    for g,(x,y) in enumerate(pairs):
        mask=both[g];m=gs[mask,k+g]
        first=np.floor((m+1)*v[mask,x]/(v[mask,x]+v[mask,y])).astype(np.int16)
        out[mask,x]=np.minimum(first,m);out[mask,y]=m-out[mask,x]
    return out.astype(np.int8)

class CellIntegrator:
    """Probability of exact seats via disjoint D'Hondt divisor-cell charts.

For group counts s, choose last-seat pivot p. Set u_p=0 and other u in [0,1],
g=(s+u)/(120+sum(u)). The chart Jacobian is s_p/(120+sum(u))**G.
Pivot sampling with probability s_p/120 gives weight 120/T**G. Internal pair
fraction lies in [a/(m+1),(a+1)/(m+1)]. All threshold conditions are checked.
This representation covers candidates with no group at the majority cap.
"""
    def __init__(self, posterior: dict, qualified: tuple[int,...], *, quadrature=32):
        self.posterior=posterior; self.qualified=tuple(sorted(qualified))
        if 0 not in self.qualified: raise ValueError('This search requires Likud qualified; other regimes must be assessed separately')
        self.major=[x-1 for x in self.qualified if x!=0]
        self.minor=[x-1 for x in range(1,len(posterior['keys'])) if x not in self.qualified]
        pairs=[tuple(pair) for pair in posterior['pairs'] if all(x in self.qualified for x in pair)]
        paired={x for pair in pairs for x in pair}
        self.groups=pairs+[(x,) for x in self.qualified if x not in paired]
        self.pair_count=len(pairs); d=len(self.major); b=len(self.minor)
        # Generalized Laguerre integrates Gamma(error_shape, rate=1) mixing.
        nodes,w=roots_genlaguerre(quadrature,posterior['error_shape']-1)
        w=w/np.exp(gammaln(posterior['error_shape']))
        means=[];chols=[];regress=[];conditional=[];belowmeans=[];logdet=[];weights=[]
        c=np.eye(len(posterior['keys'])-1)+np.ones((len(posterior['keys'])-1,)*2)
        for gm,gc,gw in zip(posterior['means'],posterior['covariances'],posterior['weights']):
            for x,weight in zip(nodes,w):
                cov=gc+posterior['error_scale']/x*c
                ca=cov[np.ix_(self.major,self.major)];chol=np.linalg.cholesky(ca)
                cross=cov[np.ix_(self.minor,self.major)]
                reg=np.linalg.solve(ca,cross.T).T
                cb=cov[np.ix_(self.minor,self.minor)]-reg@cross.T
                means.append(gm[self.major]);belowmeans.append(gm[self.minor]);chols.append(chol)
                regress.append(reg);conditional.append(np.linalg.cholesky((cb+cb.T)/2))
                logdet.append(np.log(np.diag(chol)).sum());weights.append(gw*weight)
        self.means=np.array(means);self.belowmeans=np.array(belowmeans)
        self.inverse=np.linalg.inv(np.array(chols));self.regress=np.array(regress);self.conditional=np.array(conditional)
        self.logdet=np.array(logdet);self.weights=np.array(weights)
        # Tilt to the peak density of each major-party Gaussian, with exact weights.
        logproposal=np.log(np.maximum(self.weights,1e-300))-self.logdet
        self.logproposal=logproposal-logsumexp(logproposal)
        self.proposal=np.exp(self.logproposal);self.cdf=np.cumsum(self.proposal);self.cdf[-1]=1
        self.dimension=(len(self.groups)-1)+self.pair_count+b+2
        self.draw_cache={}

    def _draws(self,power,seed):
        cache=(power,seed)
        if cache not in self.draw_cache:
            u=qmc.Sobol(self.dimension,scramble=True,seed=seed).random_base2(power)
            comp=np.searchsorted(self.cdf,u[:,0]); b=len(self.minor)
            normals=ndtri(np.clip(u[:,-b:],1e-15,1-1e-15)) if b else np.empty((len(u),0))
            if power<=14:
                if len(self.draw_cache)>=8:self.draw_cache.pop(next(iter(self.draw_cache)))
                self.draw_cache[cache]=(u,comp,normals)
            else:return u,comp,normals
        return self.draw_cache[cache]

    def estimate(self,seats: np.ndarray, *, power=12, seed=1, return_points=False):
        seats=np.asarray(seats); S=int(seats.sum())
        if S!=120 or tuple(np.flatnonzero(seats))!=self.qualified:
            raise ValueError('Candidate must match qualified set and total 120')
        counts=np.array([sum(seats[x] for x in group) for group in self.groups])
        if max(counts)>=60:raise ValueError('Candidate intersects the statutory majority-cap regime')
        u,comp,normals=self._draws(power,seed); n=len(u); G=len(counts)
        pivot=np.searchsorted(np.cumsum(counts)/S,u[:,1])
        cube=np.zeros((n,G)); row=np.arange(n)
        for g in range(G):
            mask=pivot!=g
            cube[mask,g]=u[mask,2+g-(pivot[mask]<g)]
        T=S+cube.sum(axis=1); group=(counts+cube)/T[:,None]
        q=np.zeros((n,len(seats))); logjac=np.log(S)-G*np.log(T)
        pairindex=0
        for g,members in enumerate(self.groups):
            if len(members)==1:q[:,members[0]]=group[:,g]
            else:
                x,y=members;fraction=(seats[x]+u[:,2+G-1+pairindex])/(counts[g]+1)
                q[:,x]=group[:,g]*fraction;q[:,y]=group[:,g]*(1-fraction)
                logjac+=np.log(group[:,g])-np.log(counts[g]+1);pairindex+=1
        logjac-=np.log(q[:,self.qualified]).sum(axis=1)
        major=np.log(q[:,[x+1 for x in self.major]]/q[:,[0]])
        diff=major-self.means[comp]
        whitened=np.einsum('nij,nj->ni',self.inverse[comp],diff)
        logdensity=-.5*(len(self.major)*np.log(2*np.pi)+(whitened**2).sum(axis=1))-self.logdet[comp]
        logweights=logjac+logdensity+np.log(np.maximum(self.weights[comp],1e-300))-self.logproposal[comp]
        conditional_mean=self.belowmeans[comp]+np.einsum('nij,nj->ni',self.regress[comp],diff)
        b=len(self.minor); standard=np.zeros((n,b)); chol=self.conditional[comp]
        # All b excluded parties must individually be below kappa of modeled
        # support. This implies exp(z_b)*q_ref < kappa/(1-b*kappa).
        # Sequential truncated-normal importance sampling integrates rare
        # threshold regimes without waiting for an unconditioned tail hit.
        kappa=self.posterior['threshold']/(1-self.posterior['residual_mass'])
        upper=np.log(kappa/(1-b*kappa))-np.log(q[:,0])
        for j in range(b):
            previous=np.einsum('nj,nj->n',chol[:,j,:j],standard[:,:j])
            limit=(upper-conditional_mean[:,j]-previous)/chol[:,j,j]
            mass=ndtr(limit)
            logweights+=np.log(np.maximum(mass,1e-300))
            standard[:,j]=ndtri(np.clip(u[:,-b+j]*mass,1e-300,1-1e-15))
        below=conditional_mean+np.einsum('nij,nj->ni',chol,standard)
        # y_b = log(v_b / sum qualified votes) = z_b + log(q_reference).
        relative=np.exp(below)*q[:,[0]]
        qualified_mass=(1-self.posterior['residual_mass'])/(1+relative.sum(axis=1))
        votes=q*qualified_mass[:,None]
        if self.minor:votes[:,[x+1 for x in self.minor]]=relative*qualified_mass[:,None]
        valid=(votes[:,self.qualified]>=self.posterior['threshold']).all(axis=1)
        if self.minor:valid&=(votes[:,[x+1 for x in self.minor]]<self.posterior['threshold']).all(axis=1)
        values=np.exp(logweights)*valid
        if return_points:return float(values.mean()),votes[valid]
        return float(values.mean())

def estimate_replicated(integrator, seats, *, power=16, seeds=range(8)):
    values=np.array([integrator.estimate(seats,power=power,seed=int(seed)) for seed in seeds])
    return {'probability':float(values.mean()),'replicate_standard_error':float(values.std(ddof=1)/np.sqrt(len(values))),
            'replicates':values.tolist(),'points_per_replicate':2**power,'replicate_count':len(values)}
