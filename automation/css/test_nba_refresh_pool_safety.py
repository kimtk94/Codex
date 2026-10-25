import unittest
from unittest.mock import patch
import nba_refresh_pool as target


class FakeValues:
    def __init__(self, sources):
        self.sources=sources
        self.writes=[]
    def get(self,spreadsheetId,range,valueRenderOption):
        class Request:
            def __init__(self,value):self.value=value
            def execute(self):return {"values":self.value}
        name=range.split("'!")[0][1:]
        return Request(self.sources[name])
    def clear(self,**kwargs):
        self.writes.append(("clear",kwargs))
        raise AssertionError("dry run must never clear data")
    def update(self,**kwargs):
        self.writes.append(("update",kwargs))
        raise AssertionError("dry run must never update data")


class FakeAPI:
    def __init__(self,values,capacity=2000):
        self.reader=values
        self.capacity=capacity
    def values(self):return self.reader
    def get(self,**kwargs):
        class Request:
            def __init__(self,capacity):self.capacity=capacity
            def execute(self):return {"sheets":[{"properties":{"title":"NBA Action Pool","gridProperties":{"rowCount":self.capacity}}}]}
        return Request(self.capacity)


class LiveDryRunTests(unittest.TestCase):
    def test_read_all_sources_without_mutation(self):
        samples={
          "BI Followup Unified":[["Priority","Source","Record ID","Original Status"],["P0","CSS","ACT-1","미검토"]],
          "Lead Email Followup":[["Lead ID","Sent Mail Count","Description Class"],["Lead-1","0","DESCRIPTION_PRESENT"]],
          "BI Unanswered Triage":[["Thread UID","Aging Days","Effective Queue"],["inbox:1","3","REVIEW_2D"]],
        }
        values=FakeValues(samples)
        api=FakeAPI(values)
        with patch.object(target,"date") as mockdate:
            mockdate.today.return_value=__import__("datetime").date(2026,10,26)
            self.assertEqual(target.sync(api,dry_run=True),3)
        self.assertEqual(values.writes,[])

    def test_overflow_refuses_write(self):
        samples={
          "BI Followup Unified":[["Priority","Source","Record ID"],["P0","CSS","ACT-1"]],
          "Lead Email Followup":[["Lead ID"]],
          "BI Unanswered Triage":[["Thread UID"]],
        }
        values=FakeValues(samples)
        with self.assertRaises(ValueError):
            target.sync(FakeAPI(values,capacity=1),dry_run=False)
        self.assertEqual(values.writes,[])


if __name__=="__main__":
    unittest.main()
