import unittest
from independent_review import extract_text, anchors_near, ANCHORS

class AnchorTests(unittest.TestCase):
    def test_html_visible_anchors(self):
        text = extract_text(b"<table><tr><td>2018 First Quarter $174.08 $153.45</td><td>0.37837</td></tr></table>", "html")
        self.assertTrue(anchors_near(text, ANCHORS["QQQ_2018_SEC_2020_Q3_TABLE"]))
    def test_script_not_evidence(self):
        text = extract_text(b"<script>2018 First Quarter $174.08 $153.45 0.37837</script><p>unrelated</p>", "html")
        self.assertFalse(anchors_near(text, ANCHORS["QQQ_2018_SEC_2020_Q3_TABLE"]))
    def test_distant_not_evidence(self):
        a,b = ANCHORS["QLD_2025_FORM_8937_SPLIT"]
        self.assertFalse(anchors_near(a + "x"*1900 + b, (a,b)))
    def test_missing_not_evidence(self):
        self.assertFalse(anchors_near("November 19, 2025", ANCHORS["QLD_2025_FORM_8937_SPLIT"]))
    def test_nearby_case_insensitive(self):
        self.assertTrue(anchors_near("november 19, 2025 2:1 SHARE SPLIT", ANCHORS["QLD_2025_FORM_8937_SPLIT"]))

if __name__ == "__main__":
    unittest.main()
