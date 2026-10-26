import numpy as np
from knesset_forecast.joint_mode import allocate_batch,CellIntegrator
from knesset_forecast.electoral import allocate_seats

def test_batch_allocator_matches_rational_engine_including_threshold_patterns():
    rng=np.random.default_rng(41);pairs=[(0,1),(2,3),(4,5)]
    votes=rng.dirichlet(np.full(9,1.3),size=1000)*.993
    actual=allocate_batch(votes,pairs)
    for v,a in zip(votes,actual):
        # Fixed residual is split into known subthreshold lists.
        values={str(i):float(x) for i,x in enumerate(v)}|{'residual':.007}
        expected=allocate_seats(values,[(str(x),str(y)) for x,y in pairs],tie_break='lexicographic')
        assert list(a)==[expected[str(i)] for i in range(9)]

def example():
    # Four parties avoid majority-cap intersections in the tested cell.
    return {'keys':['a','b','c','d'],'weights':np.array([1.]),'means':np.array([[.1,-.2,-.4]]),
            'covariances':np.array([np.eye(3)*.015]),'error_shape':3.5,'error_scale':.08,
            'pairs':[(2,3)],'residual_mass':.007,'threshold':.0325}

def test_cell_chart_every_point_allocates_to_requested_parliament():
    p=example(); cell=CellIntegrator(p,(0,1,2,3),quadrature=24)
    candidate=np.array([32,35,29,24])
    probability,points=cell.estimate(candidate,power=10,return_points=True)
    assert probability>0
    assert np.all(allocate_batch(points,p['pairs'])==candidate)

def test_cell_integration_agrees_with_independent_direct_monte_carlo():
    from knesset_forecast.joint_mode import sample_votes
    p=example();candidate=np.array([32,35,29,24])
    cell=CellIntegrator(p,(0,1,2,3),quadrature=32)
    estimates=np.array([cell.estimate(candidate,power=13,seed=s) for s in range(4)])
    rng=np.random.default_rng(131);hits=0;n=800000
    for _ in range(8):
        seats=allocate_batch(sample_votes(p,n//8,rng),p['pairs'])
        hits+=np.all(seats==candidate,axis=1).sum()
    observed=hits/n;se=np.sqrt(max(hits,1))/n
    assert hits>30
    assert abs(estimates.mean()-observed)<4*se

def test_truncated_importance_integration_with_a_failed_party():
    from knesset_forecast.joint_mode import sample_votes
    p=example();p['means']=np.array([[-.1,-.2,-2.3]])
    candidate=np.array([44,42,34,0])
    cell=CellIntegrator(p,(0,1,2),quadrature=48)
    estimates=np.array([cell.estimate(candidate,power=14,seed=s) for s in range(4)])
    probability,points=cell.estimate(candidate,power=10,return_points=True)
    assert np.all(points[:,3]<p['threshold'])
    assert np.all(allocate_batch(points,p['pairs'])==candidate)
    rng=np.random.default_rng(76);hits=0;n=800000
    for _ in range(8):
        seats=allocate_batch(sample_votes(p,n//8,rng),p['pairs'])
        hits+=np.all(seats==candidate,axis=1).sum()
    assert hits>30
    assert abs(estimates.mean()-hits/n)<4*np.sqrt(hits)/n