#!/usr/bin/env python3
"""HCC Stage35 source-only MD5-verified original LiverHccSeg metadata preflight.
Does not establish patient pretreatment chronology, same RNA-sampled lesion or eligible n.
"""
import argparse,csv,hashlib,io,json,os,re,zipfile
from collections import Counter,defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path("research/hcc")
SRC="https://zenodo.org/records/8179129"
MD5="37806f09955aa198ab8e50e0e2929da7"
INDEX=ROOT/"HCC_MRI_14_PREOUTCOME_INDEX_LESION_SELECTION_20261030.csv"
REVIEW=ROOT/"HCC_MRI14_QUALIFIED_REVIEW_EVIDENCE_MATRIX_20261031.csv"
RNA=ROOT/"HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv"
NS={"x":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PAT=re.compile(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}",re.I)
UID=re.compile(r"(?:[0-9]+\.)+[0-9]+")
COLS=("patient_id","selected_MRI_tumor","source_workbook_patient_rows",
"source_worksheets","explicit_study_UID_candidates","explicit_series_UID_candidates",
"source_UID_status","MRI_before_HCC_therapy","same_index_tumor_RNA","independent_radiology",
"qualified_clinical_patient","MRI_RNA_tests","claim_ceiling")

def must(ok,err):
    if not ok:raise ValueError(err)

def csv_rows(p):
    with p.open(newline="",encoding="utf8") as f:return list(csv.DictReader(f))

def cohort():
    a={r["patient_id"]:r for r in csv_rows(INDEX)}
    b={r["patient_id"]:r for r in csv_rows(REVIEW)}
    c={r["patient_id"]:r for r in csv_rows(RNA)}
    must(len(a)==14 and len(b)==14 and len(c)==14 and set(a)==set(b)==set(c),
         "SOURCE_14_PATIENT_ROSTER_DRIFT")
    for pid in a:
        must(int(a[pid]["representative_tumor_number"])==int(b[pid]["selected_tumor_number"]),
             "FROZEN_INDEX_TUMOR_CHANGED")
        must(b[pid]["RNA_same_selected_tumor"]=="NOT_ASSESSED" and
             b[pid]["MRI_pre_HCC_treatment"]=="NOT_ASSESSED" and
             b[pid]["qualified_patient_eligible"]=="NOT_ASSESSED",
             "EXPERT_CLINICAL_SOURCE_EVIDENCE_REQUIRES_REVIEW")
        must(c[pid]["aliquot_barcode"].startswith(pid+"-01"),"GDC_PRIMARY_RNA_BARCODE_CHANGED")
    return a

def colnum(a):
    m=re.match(r"([A-Z]+)[0-9]+$",a)
    must(m is not None,"EXCEL_CELL_COORDINATE_INVALID")
    n=0
    for c in m.group(1):n=n*26+ord(c)-64
    return n-1

def workbook(data):
    must(len(data)<3000000 and hashlib.md5(data).hexdigest()==MD5,
         "ZENODO_OFFICIAL_METADATA_XLSX_MD5_CHANGED")
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=set(z.namelist())
        must(all(not x.startswith("/") and ".." not in x.split("/") for x in names),
             "ZIP_UNSAFE_SOURCE_PATH")
        ss=[]
        if "xl/sharedStrings.xml" in names:
            root=ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("x:si",NS):
                ss.append("".join(t.text or "" for t in si.findall(".//x:t",NS)))
        for name in sorted(x for x in names if re.fullmatch(r"xl/worksheets/sheet[0-9]+[.]xml",x)):
            root=ET.fromstring(z.read(name))
            rows=[]
            for r in root.findall(".//x:sheetData/x:row",NS):
                vals={}
                for c in r.findall("x:c",NS):
                    address=c.attrib.get("r","")
                    if not address:continue
                    i=colnum(address)
                    t=c.attrib.get("t","")
                    v=c.find("x:v",NS)
                    inline=c.find("x:is",NS)
                    if t=="s" and v is not None:
                        j=int(v.text or "-1")
                        must(0<=j<len(ss),"BAD_EXCEL_SHARED_STRING_REF")
                        value=ss[j]
                    elif inline is not None:
                        value="".join(a.text or "" for a in inline.findall(".//x:t",NS))
                    else:
                        value=(v.text or "") if v is not None else ""
                    if value.strip():vals[i]=value.strip()
                if vals:rows.append(vals)
            out.append((name,rows))
    must(out and any(rs for _,rs in out),"NO_USABLE_OFFICIAL_METADATA_WORKSHEET")
    return out

def header(s):
    h=re.sub(r"[^a-z0-9]","",s.casefold())
    if h in ("studyinstanceuid","dicomstudyinstanceuid"):return "study"
    if h in ("seriesinstanceuid","dicomseriesinstanceuid"):return "series"
    return None

def reconcile(tabs,ids):
    matched=defaultdict(lambda:{"rows":0,"sheets":set(),"study":set(),"series":set()})
    inventory=[];header_counts=Counter()
    for name,rows in tabs:
        fields={}
        for row in rows[:12]:
            for j,v in row.items():
                typ=header(v)
                if typ:fields[j]=typ
        header_counts.update(fields.values())
        n=0
        for row in rows:
            seen=set(pid.upper() for v in row.values() for pid in PAT.findall(v)) & ids
            for pid in seen:
                n+=1
                d=matched[pid];d["rows"]+=1;d["sheets"].add(name)
                for j,typ in fields.items():
                    if j in row:
                        candidate=row[j].strip()
                        if UID.fullmatch(candidate) and len(candidate)<=64:
                            d[typ].add(candidate)
        inventory.append({"sheet":name,"nonempty_rows":len(rows),
                          "literal_frozen_patient_row_matches":n,
                          "explicit_study_series_column_headers":dict(Counter(fields.values())),
                          "first_nonempty_row_cells":list(rows[0].values())[:25] if rows else []})
    return matched,inventory,dict(header_counts)

def run(original,out):
    ids=cohort()
    match,sheets,headers=reconcile(workbook(original),set(ids))
    rows=[]
    for pid in sorted(ids):
        d=match.get(pid) or {"rows":0,"sheets":set(),"study":set(),"series":set()}
        stat=("UID_CANDIDATE_NOT_ORIGINAL_DICOM_CONFIRMED"
              if d["study"] and d["series"] and d["rows"] else
              "SOURCE_EXCEL_PATIENT_FOUND_UID_INCOMPLETE" if d["rows"]
              else "SOURCE_EXCEL_PATIENT_NOT_FOUND")
        rows.append(dict(patient_id=pid,
          selected_MRI_tumor=ids[pid]["representative_tumor_number"],
          source_workbook_patient_rows=d["rows"],
          source_worksheets="|".join(sorted(d["sheets"])),
          explicit_study_UID_candidates="|".join(sorted(d["study"])),
          explicit_series_UID_candidates="|".join(sorted(d["series"])),
          source_UID_status=stat,
          MRI_before_HCC_therapy="NOT_ASSESSED",
          same_index_tumor_RNA="NOT_ASSESSED",
          independent_radiology="NOT_ASSESSED",
          qualified_clinical_patient="NOT_ASSESSED",
          MRI_RNA_tests=0,claim_ceiling="S0"))
    summary={
      "stage":"HCC_STAGE35_OFFICIAL_LIVERHCCSEG_EXCEL_DICOM_METADATA_SOURCE_PREFLIGHT",
      "source_original_zenodo_record":SRC,
      "source_md5":MD5,
      "frozen_TCGA_LIHC_patients":14,
      "patients_with_literal_original_source_metadata_rows":sum(int(r["source_workbook_patient_rows"]>0) for r in rows),
      "patients_with_both_explicit_source_uid_candidate_columns":sum(int(r["source_UID_status"]=="UID_CANDIDATE_NOT_ORIGINAL_DICOM_CONFIRMED") for r in rows),
      "source_worksheet_count":len(sheets),"source_worksheet_inventory":sheets,
      "explicit_uid_header_counts":headers,
      "source_Study_and_Series_UID_confirmed_against_original_DICOM":0,
      "MRI_before_HCC_therapy_episode_verified":0,
      "RNA_sample_same_MRI_index_lesion_verified":0,
      "clinical_eligible_n":"NOT_ASSESSED",
      "MRI_RNA_biological_tests":0,"claim_ceiling":"S0",
      "decision":"SOURCE_ORIGINAL_EXCEL_METADATA_AUDITED_CLINICAL_PAIRED_COHORT_HOLD",
      "TCIA_DICOM_shifted_dates_vs_GDC_relative_days_join_authorized":False}
    must(len(rows)==14 and all(r["claim_ceiling"]=="S0" for r in rows),
         "INVALID_STAGE35_CLINICAL_GATE")
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stage35_frozen14_original_source_UID_candidates.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLS);w.writeheader();w.writerows(rows)
    (out/"stage35_original_excel_source_metadata_audit.json").write_text(json.dumps(summary,indent=2)+"\n")
    lines=["# Stage35 official source metadata inventory",
      "", "Original source: "+SRC+"; verified official source XLSX MD5 "+MD5,
      "", "Original 14 MRI subjects found in source metadata: "+
      str(summary["patients_with_literal_original_source_metadata_rows"])+"/14",
      "Cases with BOTH explicit Study/Series UID candidate values: "+
      str(summary["patients_with_both_explicit_source_uid_candidate_columns"])+"/14",
      "Neither case matching nor UID candidate proves pretreatment imaging or exact sampled tumor.",
      "Full original DICOM identity: NOT VERIFIED; MRI-GDC chronology and same tumor RNA: HOLD.",
      "Qualified clinical eligible n NOT_ASSESSED, biological MRI-RNA 0/12, claim S0.","",
      "| Patient | Source metadata rows | Study UID candidates | Series UID candidates |",
      "|---|---:|---:|---:|"]
    for r in rows:
        lines.append("| "+r["patient_id"]+" | "+str(r["source_workbook_patient_rows"])+" | "+
                     str(len([v for v in r["explicit_study_UID_candidates"].split("|") if v]))+" | "+
                     str(len([v for v in r["explicit_series_UID_candidates"].split("|") if v]))+" |")
    report="\n".join(lines)+"\n"
    (out/"stage35_source_uid_preflight_report.md").write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write(report)
    print("HCC_STAGE35_OFFICIAL_ORIGINAL_METADATA_MD5_SOURCE_AUDIT",json.dumps({
       k:v for k,v in summary.items() if k!="source_worksheet_inventory"},sort_keys=True),flush=True)

def offline():
    assert header("Study Instance UID")=="study"
    assert header("SeriesInstanceUID")=="series"
    assert header("Sequence") is None
    assert header("StudyDate") is None
    assert UID.fullmatch("TCGA-BC-A10Y") is None
    assert len(cohort())==14
    print("HCC_STAGE35_EXPLICIT_UID_HEADER_AND_FROZEN_14_NEGATIVE_TEST_PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline-test",action="store_true")
    p.add_argument("--official-xlsx",type=Path)
    p.add_argument("--out-dir",type=Path,default=Path("artifacts/hcc_stage35_source_metadata"))
    a=p.parse_args()
    offline()
    if a.offline_test:return
    must(a.official_xlsx and a.official_xlsx.is_file(),"OFFICIAL_ORIGINAL_XLSX_REQUIRED")
    run(a.official_xlsx.read_bytes(),a.out_dir)
if __name__=="__main__":main()
