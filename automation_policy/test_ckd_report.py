"""Regression tests for CKD evidence report without uploading any original TSV."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from unittest.mock import patch

from automation_policy.ckd_report import produce

class CKDReportTests(unittest.TestCase):
    def test_end_to_end_synthetic_report(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"inputs"
            source.mkdir()
            datasets={
                "STAGE2B_COLOC_DEFAULT.tsv":[{"gene_symbol":"GENEA","PP.H4":"0.92"}],
                "STAGE2C_SUSIE_DEFAULT.tsv":[{"gene_symbol":"GENEA","stage2b_ABF_PP.H4":"0.92","max_PP.H4":"0.9"}],
                "STAGE3A_KIDNEY_EVIDENCE.tsv":[{"gene_symbol":"GENEA","stage2_abf_h4":"0.92"}],
                "STAGE3B_INTEGRATED_EVIDENCE.tsv":[{"gene_symbol":"GENEA","stage2_abf_h4":"0.92"}],
            }
            for name, records in datasets.items():
                with (source/name).open("w",newline="") as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(records[0]),delimiter="\t")
                    writer.writeheader()
                    writer.writerows(records)
            mat=MagicMock()
            pyplot=MagicMock()
            fig,ax=MagicMock(),MagicMock()
            pyplot.subplots.return_value=(fig,ax)
            with patch.dict("sys.modules",{"matplotlib":mat,"matplotlib.pyplot":pyplot}):
                result=produce(source,Path(d)/"report")
            fig.savefig.assert_called_once()
            self.assertEqual(result["status"],"CROSS_STAGE_QC_PASS")
            self.assertFalse(result["scientific_recomputation"])
            self.assertTrue((Path(d)/"report/ckd-summary.json").is_file())
            self.assertTrue((Path(d)/"report/ckd-summary.md").is_file())
            self.assertTrue((Path(d)/"report/ckd-summary.json").is_file())
