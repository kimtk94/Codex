import copy,json,unittest
from staging_env_scope_gate import assess,SNAPSHOT
class EnvScopeTests(unittest.TestCase):
    def setUp(self):self.data=json.loads(SNAPSHOT.read_text())
    def test_current_holds_with_privileged_names(self):
        v=assess(self.data)
        self.assertEqual(v["reason"],"PRIVILEGED_VARS_PRESENT_IN_STAGING")
        self.assertEqual(v["risky_names"],["BLOB_READ_WRITE_TOKEN","INVESTMENT_HUB_INGEST_SECRET"])
    def test_no_decrypted_value_in_snapshot(self):
        self.assertFalse(self.data["decrypted_values_retrieved"])
    def test_wrong_project_fails(self):
        self.assertEqual(assess({**self.data,"project_id":"wrong"})["reason"],"WRONG_PROJECT")
    def test_absent_inventory_fails(self):
        self.assertEqual(assess({**self.data,"variables":None})["reason"],"ENV_INVENTORY_NOT_ATTESTED")
    def test_no_sensitive_vars_still_requires_sso(self):
        x=copy.deepcopy(self.data);x["variables"]=[]
        self.assertEqual(assess(x)["reason"],"STAGING_ACCESS_PROTECTION_MISSING")
    def test_sso_alone_requires_credential_isolation(self):
        x=copy.deepcopy(self.data);x["variables"]=[];x["sso_enabled"]=True
        self.assertEqual(assess(x)["reason"],"CREDENTIAL_ISOLATION_NOT_ATTESTED")
    def test_even_hypothetical_safe_conditions_do_not_authorize(self):
        x=copy.deepcopy(self.data);x.update(variables=[],sso_enabled=True,blob_isolation_verified=True,ingest_isolation_verified=True)
        self.assertFalse(assess(x)["deployment_authorized"])
if __name__=="__main__":unittest.main()
