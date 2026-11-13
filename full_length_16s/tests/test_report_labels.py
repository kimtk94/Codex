"""Verify uploaded KIST Excel reporting/group label mapping, including controls."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from full16s import report_labels

def test_uploaded_excel_group_labels():
    cases=[
      ("KCT_W1_01","FKDN260619013-1A","CT.W1.01","CT.W1"),
      ("K905_W1_10","FKDN260619042-1A","M905.W1.10","M905.W1"),
      ("KCT_W3_10","FKDN260619082-1A","CT.W3.10","CT.W3"),
      ("K902_W3_02","FKDN260619084-1A","M902.W3.02","M902.W3"),
      ("KUW_01","FKDN260618712-1A","Blank.W.01","Blank.W"),
      ("KUD_04","FKDN260618719-1A","Blank.D.04","Blank.D"),
      ("KCR_04","FKDN260618723-1A","CT.04","Control"),
      ("KDR_04","FKDN260618727-1A","TR.04","Drought"),
      ("PC","FKDN260619103-1A","PC.Motion",""),
      ("NC","FKDN260619104-1A","NC.Motion",""),
      ("PC","FKDN260618728-1A","PC.Drought",""),
      ("NC","FKDN260618729-1A","NC.Drought",""),
    ]
    for sample, fkdn, report, group in cases:
        assert report_labels(sample,fkdn)==(report,group)
