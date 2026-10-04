import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

spec = importlib.util.spec_from_file_location("css_to_vault", SCRIPTS / "css_to_vault.py")
css = importlib.util.module_from_spec(spec)
spec.loader.exec_module(css)

spec2 = importlib.util.spec_from_file_location("drive_research_to_vault", SCRIPTS / "drive_research_to_vault.py")
research = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(research)


class MasterOSV2Test(unittest.TestCase):
    def test_institution_aliases(self):
        self.assertEqual(css.normalize_institution("Ehwa Univ."), "Ewha Univ.")
        self.assertEqual(css.normalize_institution("Kyungpook Univ."), "Kyungpook National Univ.")
        self.assertEqual(css.normalize_institution("KAIST Univ."), "KAIST")
        self.assertEqual(
            css.normalize_institution("50", "Korea-50-Korea Institute of Oriental Medicine-Amplicon"),
            "KIOM",
        )
        self.assertEqual(
            css.normalize_institution("4", "Korea-4-PWGS-20Gb-WOBI-University of Missouri-SoyonPark"),
            "University of Missouri",
        )

    def test_service_taxonomy_preserves_structured_categories(self):
        self.assertEqual(
            css.classify_service("mRNA-Seq", "Korea-AgingLab-human-WGS-90Gb"),
            "mRNA-Seq",
        )
        self.assertEqual(
            css.classify_service("Other", "Korea-APQA-72-mWGS-1Gb"),
            "Microbial WGS",
        )
        self.assertEqual(
            css.classify_service("WGS", "Korea-Ewha-75-Animal-WGS-12Gb"),
            "Animal WGS",
        )
        self.assertEqual(
            css.classify_service("WGS", "Korea-Kyungpook-84-WGS-1Gb"),
            "Microbial WGS",
        )
        self.assertEqual(
            css.classify_service("Other", "Korea-Yonsei-6-Human-mRNA-Seq-6Gb"),
            "mRNA-Seq",
        )

    def test_ckd_candidate_generation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "IS_Analysis_V3"
            stage = root / "results" / "ckd" / "stage3b_celltype"
            stage.mkdir(parents=True)
            (stage / "STAGE3B_INTEGRATED_EVIDENCE.tsv").write_text(
                "gene_symbol\tkidney_cell_type\tscore\n"
                "SDCCAG8\tmacrophages\t0.98\n"
                "UMOD\tloop_of_Henle\t0.95\n",
                encoding="utf-8",
            )
            vault = Path(td) / "vault"
            research.build(root, vault)
            master = (vault / "01_RESEARCH" / "CKD" / "CKD_MASTER.md").read_text(encoding="utf-8")
            self.assertIn("Candidate genes detected: **2**", master)
            self.assertTrue((vault / "01_RESEARCH" / "CKD" / "Candidates" / "SDCCAG8.md").exists())
            self.assertTrue((vault / "01_RESEARCH" / "CKD" / "Candidates" / "UMOD.md").exists())


if __name__ == "__main__":
    unittest.main()