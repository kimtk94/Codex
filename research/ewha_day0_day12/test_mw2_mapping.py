import importlib.util
import unittest
from pathlib import Path

SRC = Path(__file__).with_name("mw2_mapping_pipeline.py")
SPEC = importlib.util.spec_from_file_location("mw2", SRC)
mw2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mw2)


class Mw2VariantQC(unittest.TestCase):
    def setUp(self):
        self.pairs = {}
        for sample in mw2.g.SAMPLES:
            is_day12 = sample.startswith("Day12")
            self.pairs[sample] = {"GT": "1" if is_day12 else "0",
                                  "DP": 60, "GQ": 95, "AD": ""}
        self.coverage = {
            s: {mw2.CHR: {"breadth_10x": .98},
                mw2.PLASMID: {"breadth_10x": .95}}
            for s in mw2.g.SAMPLES
        }

    def test_replicated_day12_chr_candidate(self):
        self.assertEqual(
            mw2.genotype_group(self.pairs, mw2.CHR, 1, self.coverage),
            "DAY12_REPLICATED_CANDIDATE"
        )

    def test_one_day12_only(self):
        self.pairs["Day12.2"]["GT"] = "0"
        self.pairs["Day12.3"]["GT"] = "0"
        self.assertEqual(
            mw2.genotype_group(self.pairs, mw2.CHR, 1, self.coverage),
            "DAY12_SINGLE_REVIEW"
        )

    def test_incomplete_baseline(self):
        self.pairs["Day0.3"]["DP"] = 0
        self.assertEqual(
            mw2.genotype_group(self.pairs, mw2.CHR, 1, self.coverage),
            "BASELINE_OR_CALLABILITY_REVIEW"
        )

    def test_plasmid_absence_not_as_genotype(self):
        self.coverage["Day0.1"][mw2.PLASMID]["breadth_10x"] = .01
        self.assertEqual(
            mw2.genotype_group(self.pairs, mw2.PLASMID, 1, self.coverage),
            "PLASMID_CALLABILITY_REVIEW"
        )

    def test_cds_overlap_annotation(self):
        ann = {mw2.CHR: [([(9, 20)], "bla", "MW123", "test enzyme")]}
        at = mw2.annotate_site(mw2.CHR, 13, "A", "G", ann)
        self.assertEqual(at["gene"], "bla")
        self.assertEqual(at["region"], "CDS_OVERLAP")
        self.assertEqual(mw2.annotate_site(mw2.CHR, 100, "A", "G", ann)["gene"], "")

    def test_accession_lengths(self):
        self.assertEqual(mw2.LENGTHS["NC_003923.1"], 2820462)
        self.assertEqual(mw2.LENGTHS["NC_005011.1"], 20654)
        self.assertEqual(sum(mw2.LENGTHS.values()), 2841116)


if __name__ == "__main__":
    unittest.main()
