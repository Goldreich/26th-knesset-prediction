"""Reproducible public adapter for the frozen October 24 forecasting inputs."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

import numpy as np
from scipy.special import softmax
from scipy.sparse.linalg import splu

from .dynamic import design,fit,measurement_covariance
from .simulation import summarize_draws


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def prepare(root: Path):
    config=read(root/'config/model.json');ballot=read(root/'data/ballot.json')
    dataset=read(root/'data/polls.json');keys=sorted(set(ballot['aliases'])-{'LIKUD'})
    start=date.fromisoformat(config['start_date']);end=date.fromisoformat(config['election_date'])
    observations=[]
    for p in dataset['polls']:
        if not p['vote_likelihood']:continue
        selected=p['included_categories'];reference=p['reference_key']
        values=np.array([p['measurements'][key]['pct']/100 for key in selected])
        ref=p['measurements'][reference]['pct']/100
        row={'id':p['id'],'firm':p['firm'],'day':(date.fromisoformat(p['fieldwork_end'])-start).days,
             'keys':selected,'y':np.log(values/ref),
             'covariance':measurement_covariance(values,ref,p['sample_size'])}
        if reference!='LIKUD':row['reference_key']=reference
        observations.append(row)
    initial=np.array([-3.7 if key in {'NOAM','ZIBUR_HAREDI','BLUE_WHITE'} else -1.2 for key in keys])
    model=design(observations,keys=keys,days=(end-start).days+1,
                 breaks=[(date.fromisoformat(d)-start).days for d in config['lineup_breaks']],initial_mean=initial)
    return config,ballot,model


def error_distribution(root: Path):
    data=read(root/'data/error_calibration.json')
    errors=np.array([np.log(row['reported_percent']/100)-np.log(row['actual_share']) for row in data['rows']])
    errors-=errors.mean();energy=float(errors@errors/(len(errors)-1))
    return data['prior_shape']+.5,data['prior_scale']+.5*energy


def complete(states,keys,ballot,sd,seed):
    modeled=['LIKUD',*keys];active=ballot['list_ids']
    selected=[key for key in modeled if ballot['aliases'][key] in active]
    z=np.column_stack([np.zeros(len(states)),states])[:,[modeled.index(key) for key in selected]]
    rng=np.random.default_rng(seed);z+=rng.normal(size=z.shape)*sd[:,None]
    support=softmax(z,axis=1)*(1-ballot['residual_mass'])
    ids=[ballot['aliases'][key] for key in selected];missing=[key for key in active if key not in ids]
    votes=np.zeros((len(states),len(active)))
    votes[:,[active.index(key) for key in ids]]=support
    votes[:,[active.index(key) for key in missing]]=ballot['residual_mass']/len(missing)
    return votes


def terminal_posterior(model,grid,ballot,shape,scale):
    """Recover marginal mixture parameters used by the exact-parliament integrator."""
    a,r,i,h=(model[key] for key in ('a','rw','initial','house'))
    aa,rr,ii,hh=(b.T@b for b in (a,r,i,h));ay=a.T@model['y'];iy=i.T@model['initial_y']
    keys=['LIKUD']+[key for key in model['keys'] if ballot['aliases'][key] in ballot['list_ids']]
    indices=np.array([model['keys'].index(key) for key in keys[1:]])+(model['days']-1)*model['k']
    selector=np.eye(model['size'])[:,indices];means=[];covariances=[];weights=[];omitted=0.
    for row in grid:
        if row['probability']<1e-12:omitted+=row['probability'];continue
        q,hs,s=row['q'],row['h'],row['s']
        factor=splu((aa/s**2+rr/q**2+ii+hh/hs**2).tocsc())
        means.append(factor.solve(ay/s**2+iy)[indices].tolist())
        c=factor.solve(selector)[indices,:];covariances.append(((c+c.T)/2).tolist());weights.append(row['probability'])
    ids=[ballot['aliases'][key] for key in keys]
    return {'keys':keys,'list_ids':ids,'all_list_ids':ballot['list_ids'],'means':means,'covariances':covariances,
            'weights':(np.array(weights)/sum(weights)).tolist(),'omitted_grid_probability_bound':omitted,
            'pairs':[(ids.index(x),ids.index(y)) for x,y in ballot['agreements'] if x in ids and y in ids],
            'residual_mass':ballot['residual_mass'],'threshold':ballot['threshold'],'error_shape':shape,'error_scale':scale}


def run(root: Path,output: Path,draws: int | None=None):
    config,ballot,model=prepare(root)
    n=draws or config['n_draws'];fitted=fit(model,n_draws=n,seed=config['seed'],**config['grid'])
    shape,scale=error_distribution(root);rng=np.random.default_rng(config['seed']+1)
    sd=np.sqrt(1/rng.gamma(shape,1/scale,size=n))
    votes=complete(fitted['state_draws'][:,-1],model['keys'],ballot,sd,config['seed']+2)
    summary=summarize_draws({'list_ids':ballot['list_ids'],'draws':votes,
                            'metadata':{'status':'conditional_scenario','assumptions':config['assumptions']}},
                           simulate_seats=True,registered_lists=ballot['list_ids'],list_universe_status='conditional_scenario',
                           conditional_ballot_id='reported_37_lists_after_blue_white_withdrawal',
                           agreements=[tuple(pair) for pair in ballot['agreements']],agreements_status='verified')
    seats=summary.pop('seat_draws');output.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output/'joint_draws.npz',vote_draws=votes,seat_draws=seats,list_ids=ballot['list_ids'])
    (output/'forecast.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'diagnostics.json').write_text(json.dumps(fitted['diagnostics'],indent=2)+'\n',encoding='utf-8')
    posterior=terminal_posterior(model,fitted['grid'],ballot,shape,scale)
    (output/'terminal_posterior.json').write_text(json.dumps(posterior,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('generated'))
    parser.add_argument('--draws',type=int,default=None)
    args=parser.parse_args()
    result=run(Path.cwd(),args.output,args.draws)
    print(f"Generated {result['n_draws']} joint vote and seat predictions in {args.output}")


if __name__=='__main__':main()
