import unittest
from unittest.mock import patch
import canonical_mail_reader as adapter
class CanonicalMailReaderTests(unittest.TestCase):
    def test_maps_staging_and_ignores_legacy(self):
        l=[""]*27;l[0]="legacy:All Emails:2";l[1]="All Emails";l[7]="<legacy@id>"
        s=[""]*27;s[0]="imap:INBOX|123|456";s[1]="CSS Git Ingest";s[4]="INBOX";s[5]="456";s[6]="123";s[7]="<new@id>";s[8]="2026-10-28T10:00:00+00:00";s[10]="contact@example.org";s[11]="taehoon.kim@novogene.com";s[14]="Test";s[20]="INBOUND"
        with patch.object(adapter.src,"api",return_value={"values":[adapter.HEAD,l,s]}):
            rows=adapter.read_staging_compatible(object())
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1][0],"INBOX|123|456")
        self.assertEqual(rows[1][1],"<new@id>")
        self.assertEqual(rows[1][15],"INBOUND")
    def test_invalid_header_fails(self):
        with patch.object(adapter.src,"api",return_value={"values":[["wrong"]]}):
            with self.assertRaisesRegex(RuntimeError,"CANONICAL_SCHEMA_MISMATCH"):
                adapter.read_staging_compatible(object())
if __name__=="__main__":unittest.main()
