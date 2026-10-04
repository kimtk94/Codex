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

spec3 = importlib.util.spec_from_file_location("research_to_vault", SCRIPTS / "research_to_vault.py")
snapshots = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(snapshots)


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
            stage2 = root / "results" / "ckd" / "stage2"
            stage2.mkdir(parents=True)
            (stage2 / "stage2_candidates.tsv").write_text(
                "gene_symbol\tanchor_rsid\n"
                "SDCCAG8\trs953492\n"
                "UMOD\trs12917707\n",
                encoding="utf-8",
            )
            stage3 = root / "results" / "ckd" / "stage3b_celltype"
            stage3.mkdir(parents=True)
            (stage3 / "STAGE3B_INTEGRATED_EVIDENCE.tsv").write_text(
                "gene_symbol\tkidney_cell_type\tscore\n"
                "SDCCAG8\tmacrophages\t0.98\n"
                "UMOD\tloop_of_Henle\t0.95\n"
                "OFFTARGET\tproximal_tubule\t0.99\n",
                encoding="utf-8",
            )
            vault = Path(td) / "vault"
            research.build(root, vault)
            master = (vault / "01_RESEARCH" / "CKD" / "CKD_MASTER.md").read_text(encoding="utf-8")
            self.assertIn("Candidate seed genes: **2**", master)
            self.assertIn("stage2/stage2_candidates.tsv", master)
            self.assertTrue((vault / "01_RESEARCH" / "CKD" / "Candidates" / "SDCCAG8.md").exists())
            self.assertTrue((vault / "01_RESEARCH" / "CKD" / "Candidates" / "UMOD.md").exists())
            self.assertFalse((vault / "01_RESEARCH" / "CKD" / "Candidates" / "OFFTARGET.md").exists())

    def test_is_master_is_thesis_main_in_obsidian(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            clones = base / "clones"
            docs = clones / "IS_Analysis_V3" / "docs"
            docs.mkdir(parents=True)
            (docs / "IS_MASTER.md").write_text(
                "# IS MASTER\n\nFGF5 / ALDH2 / SH3PXD2A / COL4A2\n",
                encoding="utf-8",
            )
            vault = base / "vault"
            snapshots.main(clones, vault)

            drive_root = base / "drive" / "IS_Analysis_V3"
            stage2 = drive_root / "results" / "ckd" / "stage2"
            stage2.mkdir(parents=True)
            (stage2 / "stage2_candidates.tsv").write_text(
                "gene_symbol\tanchor_rsid\nSDCCAG8\trs953492\n",
                encoding="utf-8",
            )
            research.build(drive_root, vault)

            self.assertTrue((vault / "01_RESEARCH" / "IS" / "IS_MASTER.md").exists())
            index = (vault / "01_RESEARCH" / "RESEARCH_INDEX.md").read_text(encoding="utf-8")
            home = (vault / "00_HOME" / "HOME.md").read_text(encoding="utf-8")
            self.assertIn("## Thesis main", index)
            self.assertLess(index.index("IS — Thesis main"), index.index("CKD — Secondary core"))
            self.assertIn("Ischemic Stroke — Thesis Main", home)
            self.assertIn("CKD — Secondary Core", home)

    def test_ckd_refresh_prunes_stale_candidate_notes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "IS_Analysis_V3"
            stage2 = root / "results" / "ckd" / "stage2"
            stage2.mkdir(parents=True)
            seed = stage2 / "stage2_candidates.tsv"
            seed.write_text(
                "gene_symbol\tanchor_rsid\nA\trs1\nB\trs2\n",
                encoding="utf-8",
            )
            vault = Path(td) / "vault"
            research.build(root, vault)
            self.assertTrue((vault / "01_RESEARCH" / "CKD" / "Candidates" / "B.md").exists())

            seed.write_text("gene_symbol\tanchor_rsid\nA\trs1\n", encoding="utf-8")
            research.build(root, vault)
            self.assertFalse((vault / "01_RESEARCH" / "CKD" / "Candidates" / "B.md").exists())


if __name__ == "__main__":
    unittest.main()