import importlib.util
import sys
import types
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
sys.modules.setdefault('incremental_sync',types.ModuleType('incremental_sync'))
spec=importlib.util.spec_from_file_location('web_body_sync',Path(__file__).with_name('web_body_sync.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class BodyTests(unittest.TestCase):
    def test_plain_preferred_over_html_and_attachment(self):
        raw=b'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n--x\nContent-Type: text/plain; charset=utf-8\n\nCustomer body\n--x\nContent-Type: text/html\n\n<p>Duplicate</p>\n--x\nContent-Type: text/plain\nContent-Disposition: attachment; filename="secret.txt"\n\nAttachment\n--x--'
        self.assertEqual(mod.body_text(BytesParser(policy=policy.default).parsebytes(raw)),'Customer body')
    def test_html_only_no_active_content(self):
        raw=b'Content-Type: text/html\n\n<p>Hello<br>World</p><script>bad()</script><style>hidden</style>'
        self.assertEqual(mod.body_text(BytesParser(policy=policy.default).parsebytes(raw)),'Hello\nWorld')
    def test_sheet_cell_limit(self):
        msg=BytesParser(policy=policy.default).parsebytes(b'Content-Type: text/plain\n\n'+b'a'*60000)
        self.assertEqual(len(mod.body_text(msg)),45000)
if __name__=='__main__': unittest.main()
