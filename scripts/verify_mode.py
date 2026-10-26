"""Re-estimate probabilities of the leading exact parliaments independently."""
import argparse
import json
from pathlib import Path
import numpy as np
from knesset_forecast.joint_mode import CellIntegrator,estimate_replicated

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--posterior',type=Path,default=Path('data/terminal_posterior.json'))
parser.add_argument('--power',type=int,default=16,help='log2 points per independent scramble')
parser.add_argument('--replicates',type=int,default=8)
args=parser.parse_args()
p=json.loads(args.posterior.read_text(encoding='utf-8'))
for key in ['means','covariances','weights']:p[key]=np.asarray(p[key])
rows=json.loads(Path('data/mode_candidates.json').read_text(encoding='utf-8'))['candidates']
results=[];integrators={}
for row in rows:
    seats=np.array(row['seats']);qualified=tuple(np.flatnonzero(seats))
    if qualified not in integrators:integrators[qualified]=CellIntegrator(p,qualified,quadrature=96)
    result=estimate_replicated(integrators[qualified],seats,power=args.power,seeds=range(81101,81101+args.replicates))
    results.append({'seats':row['seats'],**result})
    print(result['probability'],result['replicate_standard_error'],row['seats'],flush=True)
Path('generated').mkdir(exist_ok=True)
Path('generated/mode_probabilities.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
