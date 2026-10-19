import datetime as dt
import importlib.util
import unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/"grid_daily_regime_features.py"
spec=importlib.util.spec_from_file_location("regime",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
UTC=dt.timezone.utc
KST=dt.timezone(dt.timedelta(hours=9))
def sample(days,change=None):
    start=dt.date(2025,1,1)
    for i in range(days):
        day=start+dt.timedelta(days=i)
        price=(100+i if change is None else change(i))
        ts=dt.datetime.combine(day,dt.time(12),tzinfo=KST).astimezone(UTC).isoformat()
        yield (ts,price)
class TestRegime(unittest.TestCase):
    def test_warmup_cannot_trade(self):
        d=m.closed_daily_features(list(sample(60)))
        self.assertTrue(all(v["regime"]=="WARMUP" for v in d.values()))
    def test_uses_only_closed_previous_day(self):
        a=list(sample(62))
        baseline=m.closed_daily_features(a)
        mutated=a.copy();mutated[-1]=(mutated[-1][0],9999999)
        changed=m.closed_daily_features(mutated)
        final=max(baseline)
        self.assertEqual(baseline[final],changed[final])
        self.assertEqual(baseline[final]["source_through"],str(final-dt.timedelta(days=1)))
    def test_up_and_down_trends(self):
        up=m.closed_daily_features(list(sample(62)))
        down=m.closed_daily_features(list(sample(62,lambda i:1000-i)))
        self.assertEqual(up[max(up)]["regime"],"UP")
        self.assertEqual(down[max(down)]["regime"],"DOWN")
if __name__=="__main__":unittest.main()
