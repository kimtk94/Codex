import unittest
from isolated_preview_preflight import preflight
class IsolatedPreviewPreflightTests(unittest.TestCase):
    def test_isolated_source_passes(self):
        self.assertEqual(preflight()["verdict"],"PREVIEW_SOURCE_READY_NOT_DEPLOYED")
    def test_project_not_created(self):
        self.assertIs(preflight()["actual_new_project_created"],False)
    def test_staging_remains_blocked(self):
        self.assertEqual(preflight()["existing_staging_status"],"STAGING_HOLD")
    def test_requires_access_protection(self):
        self.assertTrue(preflight()["requires_independent_access_protection"])
    def test_no_deploy_authorization(self):
        self.assertFalse(preflight()["deployment_authorized"])
    def test_exact_demo_file_count(self):
        self.assertEqual(preflight()["source_file_count"],30)
    def test_source_hash_is_stable(self):
        self.assertEqual(preflight()["source_digest"],preflight()["source_digest"])
if __name__=="__main__":unittest.main()
