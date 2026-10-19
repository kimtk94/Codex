import tempfile,unittest
from pathlib import Path
from automation_policy.ckd_coloc_qc import audit

class ColocQCTests(unittest.TestCase):
    def test_valid_posterior_and_scenarios(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            txt="gene_symbol\tp1\tp2\tp12\tnsnps\tPP.H0\tPP.H1\tPP.H2\tPP.H3\tPP.H4\nGSTA3\t0.0001\t0.0001\t0.00001\t42\t0\t0\t0\t0.05\t0.95\n"
            (p/"a").write_text(txt);(p/"b").write_text(txt)
            r=audit(p/"a",p/"b")
            self.assertEqual(r["qc"],"PASS")
            self.assertFalse(r["scientific_replication"])
    def test_invalid_posterior_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            txt="gene_symbol\tp1\tp2\tp12\tnsnps\tPP.H0\tPP.H1\tPP.H2\tPP.H3\tPP.H4\nGSTA3\t0.0001\t0.0001\t0.00001\t42\t0\t0\t0\t0.2\t0.95\n"
            (p/"a").write_text(txt)
            with self.assertRaises(ValueError):
                audit(p/"a",p/"a")
