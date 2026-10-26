import numpy as np
import pytest
from knesset_forecast.dynamic import design,fit,measurement_covariance

def test_gaussian_sampler_matches_dense_posterior_and_retains_future_uncertainty():
    obs=[{'firm':firm,'day':day,'keys':['a'],'y':np.array([value]),'covariance':np.array([[.01]])}
         for firm,day,value in [('x',0,.1),('y',0,-.1),('x',1,.2),('y',1,0.)]]
    model=design(obs,keys=['a'],days=5,initial_mean=np.zeros(1))
    q,h,s=.05,.2,1.
    result=fit(model,q_grid=[q],h_grid=[h],s_grid=[s],n_draws=12000,seed=42)
    a,r,i,b=(model[k].toarray() for k in ['a','rw','initial','house'])
    precision=a.T@a+r.T@r/q**2+i.T@i+b.T@b/h**2
    covariance=np.linalg.inv(precision)
    mean=covariance@(a.T@model['y']+i.T@model['initial_y'])
    draws=result['state_draws'][:,:,0]
    assert np.max(abs(draws.mean(axis=0)-mean[:5]))<.006
    assert np.allclose(np.cov(draws.T),covariance[:5,:5],atol=.0015)
    assert draws[:,-1].var()>draws[:,1].var()+.01
    assert np.max(abs(result['house_draws'].sum(axis=1)))<1e-12
    assert result['diagnostics']['max_relative_solve_residual']<1e-10

def test_measurement_denominator_covariance_and_no_pseudo_counts():
    r=measurement_covariance(np.array([.1234,.065]),.214,503)
    assert r[0,1]>0
    assert np.linalg.eigvalsh(r).min()>0
    with pytest.raises(ValueError): measurement_covariance(np.array([0.]),.2,500)