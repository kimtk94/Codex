import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pysam

SRC = Path(__file__).with_name("gatk_haploid_pipeline.py")
SPEC = importlib.util.spec_from_file_location("ewha_gatk", SRC)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class EwhaGatkSummaryTest(unittest.TestCase):
    def test_six_haploid_samples_and_replicated_variant(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cohort = root / "cohort"
            cohort.mkdir()
            vcf = cohort / "synthetic.vcf"
            h = pysam.VariantHeader()
            h.add_meta("fileformat", value="VCFv4.2")
            h.contigs.add("contig_0001", length=1200)
            for fmt, typ in (("GT", "String"), ("DP", "Integer"), ("GQ", "Integer"), ("AD", "Integer")):
                number = "1" if fmt != "GT" else "1"
                if fmt == "AD":
                    number = "R"
                h.formats.add(fmt, number, typ, description=fmt)
            for sample in pipeline.SAMPLES:
                h.add_sample(sample)
            with pysam.VariantFile(vcf, "w", header=h) as out:
                rec = out.new_record(contig="contig_0001", start=99, alleles=("A", "G"), qual=99)
                for sample in pipeline.SAMPLES:
                    is_day12 = sample.startswith("Day12")
                    rec.samples[sample]["GT"] = (1,) if is_day12 else (0,)
                    rec.samples[sample]["DP"] = 30
                    rec.samples[sample]["GQ"] = 90
                    rec.samples[sample]["AD"] = (0, 30) if is_day12 else (30, 0)
                out.write(rec)
            out = root / "outputs" / "gatk_haploid_v1"
            out.mkdir(parents=True)
            pipeline.summarise(vcf, root, out, "test-reference")
            result = json.loads((out / "cohort" / "summary.json").read_text())
            self.assertEqual(result["sample_count"], 6)
            self.assertEqual(result["joint_alleles"], 1)
            self.assertEqual(result["replicated_day12_with_callable_day0"], 1)
            with (out / "cohort" / "joint_variant_audit.csv").open() as fh:
                rows = list(__import__("csv").DictReader(fh))
            self.assertEqual(rows[0]["classification"], "REPLICATED_GATK_ONLY_REVIEW")
            self.assertEqual(rows[0]["Day0.1_GT"], "0")
            self.assertEqual(rows[0]["Day12.2_GT"], "1")


if __name__ == "__main__":
    unittest.main()
