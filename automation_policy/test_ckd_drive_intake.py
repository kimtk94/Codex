import unittest
from automation_policy.ckd_drive_intake import validate_manifest,ALLOWED
class DriveIntakeTests(unittest.TestCase):
 def test_missing_fails(self):
  with self.assertRaises(ValueError): validate_manifest({})
 def test_invalid_hash_fails(self):
  spec={n:{"id":"safeId"+str(i),"sha256":"f"*64} for i,n in enumerate(sorted(ALLOWED))}
  self.assertTrue(validate_manifest(spec))
  spec[next(iter(spec))]["sha256"]="bad"
  with self.assertRaises(ValueError): validate_manifest(spec)
