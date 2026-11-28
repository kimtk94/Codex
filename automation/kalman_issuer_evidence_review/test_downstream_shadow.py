import copy
import unittest
from downstream_shadow import check_proof, check_lineage

class DownstreamTests(unittest.TestCase):
    def setUp(self):
        self.proof={"required_assets":26,"rows":[{"close_certified":False} for _ in range(26)],
                    "official_close_certified":0,"independent_factor_certified":0,
                    "issuer_specific_cash_gaps":2,"strategy_promoted":False,
                    "production_writes":False,"live_execution":False}
        self.lineage={"issuer_distribution_payments_certified":0,"source_finality_verified_assets":0,
                      "strategy_promoted":False,"production_writes":False,
                      "status":"TWO_CORPORATE_ACTION_SOURCE_DISAGREEMENTS_HOLD"}
    def test_hold(self):
        check_proof(self.proof);check_lineage(self.lineage)
    def test_no_close_promotion(self):
        self.proof["rows"][0]["close_certified"]=True
        with self.assertRaisesRegex(ValueError,"PROOF_PROMOTION"):check_proof(self.proof)
    def test_no_factor_promotion(self):
        self.proof["independent_factor_certified"]=1
        with self.assertRaisesRegex(ValueError,"PROOF_PROMOTION"):check_proof(self.proof)
    def test_no_cash_promotion(self):
        self.lineage["issuer_distribution_payments_certified"]=1
        with self.assertRaisesRegex(ValueError,"LINEAGE_PROMOTION"):check_lineage(self.lineage)
    def test_no_live(self):
        self.proof["live_execution"]=True
        with self.assertRaisesRegex(ValueError,"PROOF_PROMOTION"):check_proof(self.proof)

if __name__=="__main__": unittest.main()
