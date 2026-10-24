import importlib.util
from pathlib import Path
import pandas as pd
import pytest
spec=importlib.util.spec_from_file_location('adapter',Path(__file__).with_name('minute_adapter.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sample(freq='min'):
    return pd.DataFrame({'ticker':['TSLA']*6,'datetime':pd.date_range('2026-10-01 13:30Z',periods=6,freq=freq),
                         'o':[100.]*6,'h':[101.]*6,'l':[99.]*6,'c':[100.]*6})
def test_real_minute_recognition():
    df,meta=m.convert(sample())
    assert len(df)==6 and meta['TSLA']['one_minute_edges']==5
def test_15m_must_not_masquerade_as_1m():
    with pytest.raises(ValueError,match='NOT_1MIN'):
        m.convert(sample('15min'))
def test_reject_duplicate_timestamps():
    d=sample();d.loc[1,'datetime']=d.loc[0,'datetime']
    with pytest.raises(ValueError,match='duplicate'):m.convert(d)
