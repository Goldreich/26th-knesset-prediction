import json
from pathlib import Path
import numpy as np
from knesset_forecast.prediction import prepare,error_distribution

ROOT=Path(__file__).resolve().parents[1]

def test_public_inputs_define_the_issued_model():
    config,ballot,model=prepare(ROOT)
    assert model['observation_count']==69
    assert len(model['firms'])==6
    assert len(ballot['list_ids'])==37
    assert model['days']==91
    shape,scale=error_distribution(ROOT)
    assert shape==3.5
    assert np.isclose(scale,.13997195671685903)

def test_snapshot_seats_conserve_and_mode_is_a_joint_allocation():
    snapshot=json.loads((ROOT/'site/data/forecast.json').read_text(encoding='utf-8'))
    joint=json.loads((ROOT/'site/data/joint_seats.json').read_text(encoding='utf-8'))
    assert joint['forecast_id']==snapshot['forecast_id']
    assert np.all(np.asarray(joint['seat_draws']).sum(axis=1)==120)
    assert sum(snapshot['forecast']['joint_mode']['seats'].values())==120
