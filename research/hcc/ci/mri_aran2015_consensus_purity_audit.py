#!/usr/bin/env python3
"""Read Aran et al. 2015 Nature Communications CPE xlsx as PUBLIC reference QC.

Data source Supplementary Data 1 (ncomms9971-s2.xlsx).
Only a 14-patient derived match table leaves the runner. No XLSX artifacts.
No patient-level biology tests or imaging-RNA associations are performed.
XLSX read-only via Python standard library zipfile/XML.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

SOURCE="https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fncomms9971/MediaObjects/41467_2015_BFncomms9971_MOESM1236_ESM.xlsx"
ALTERNATE="https://pmc.ncbi.nlm.nih.gov/articles/instance/4671203/bin/ncomms9971-s2.xlsx"
MANIFEST="research/hcc/HCC_MRI_14_GDC_PRIMARY_TUMOR_RNA_FILE_MANIFEST_20261030.csv"
NS="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
COLUMNS=("Sample.ID","Cancer.type","ESTIMATE","ABSOLUTE","LUMP","IHC","CPE")
OUT=("patient_id","rna_sample_barcode","source_sample_barcode",
     "match_granularity","candidate_source_rows","cpe","estimate","absolute",
     "lump","ihc","published_cancer_type",
     "consensus_purity_status","clinical_eligibility","interpretation")


def fetch():
    errs=[]
    for url in (SOURCE,ALTERNATE):
        try:
            req=urllib.request.Request(url,headers={
               "User-Agent":"HCC-Purity-Public-Supplement-QC/1.0",
               "Accept-Encoding":"identity"})
            with urllib.request.urlopen(req,timeout=45) as response:
                data=response.read(2_000_001)
            if not 10000<len(data)<2_000_000 or not zipfile.is_zipfile(io.BytesIO(data)):
                raise ValueError("Not a bounded XLSX ZIP source")
            return data,url
        except Exception as exc:
            errs.append(type(exc).__name__+":"+str(exc)[:80])
    raise RuntimeError("Official supplement source unavailable: "+" | ".join(errs))


def shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root=ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(v.text or "" for v in item.iter(NS+"t"))
            for item in root.findall(NS+"si")]


def worksheet_rows(archive,path,strings):
    root=ET.fromstring(archive.read(path))
    found=[]
    for rr in root.iter(NS+"row"):
        fields={}
        for cell in rr.findall(NS+"c"):
            ref=cell.attrib.get("r","")
            m=re.match(r"([A-Z]+)",ref)
            if not m:continue
            col=0
            for ch in m.group(1):
                col=col*26+(ord(ch)-64)
            t=cell.attrib.get("t","")
            v=cell.find(NS+"v")
            if t=="inlineStr":
                value="".join(x.text or "" for x in cell.iter(NS+"t"))
            elif v is None:value=""
            elif t=="s":
                idx=int(v.text or "-1")
                value=strings[idx] if 0<=idx<len(strings) else ""
            else:
                value=v.text or ""
            fields[col-1]=value
        if fields:found.append([fields.get(i,"") for i in range(max(fields)+1)])
    return found


def normalize_header(s):
    return re.sub(r"[^a-z0-9]","",str(s).lower())


def parse_workbook(data):
    results=[]
    metadata=[]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        strings=shared_strings(archive)
        sheets=[n for n in archive.namelist()
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml",n)]
        for sheet in sheets:
            rows=worksheet_rows(archive,sheet,strings)
            metadata.append({"worksheet":sheet,"rows":len(rows),
                             "sample_preview":rows[:3]})
            for hi,header in enumerate(rows[:40]):
                norm=[normalize_header(x) for x in header]
                sample_indices=[i for i,x in enumerate(norm)
                                if x in ("sampleid","sample", "tcgasample", "samplebarcode")]
                keys={name:next((i for i,x in enumerate(norm)
                    if x==normalize_header(name)),None) for name in COLUMNS}
                if not sample_indices or keys.get("CPE") is None:
                    continue
                sample_i=sample_indices[0]
                for rr in rows[hi+1:]:
                    if sample_i>=len(rr):continue
                    sample=str(rr[sample_i]).strip().upper()
                    if not re.search(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}",sample):continue
                    d={"source_sheet":sheet,"source_sample_barcode":sample}
                    for name,i in keys.items():
                        d[name]=rr[i] if i is not None and i<len(rr) else ""
                    results.append(d)
                break
    if not results:
        raise ValueError("No workbook sheet with explicit TCGA Sample.ID and CPE columns; metadata "+str(metadata)[:1000])
    return results,metadata


def numeric(raw):
    try:
        if str(raw).strip().lower() in ("","na","nan","null","#n/a","not available"):
            return None
        value=float(raw)
        if not 0<=value<=1:raise ValueError("Purity outside 0–1")
        return value
    except (TypeError,ValueError):return None


def join(manifest,sources):
    output=[]
    for r in manifest:
        pid=r["patient_id"]
        bar=r["aliquot_barcode"][:16].upper()
        candidates=[s for s in sources if s["source_sample_barcode"].startswith(pid)]
        same=[s for s in candidates if s["source_sample_barcode"][:16]==bar]
        chosen=same if same else candidates
        if not chosen:
            status="NO_PUBLISHED_PATIENT"
            granularity="NONE"
        elif not same:
            status="PATIENT_ONLY_UNSAFE_AS_SAMPLE_PROXY"
            granularity="PATIENT_ONLY"
        elif len(same)>1:
            status="AMBIGUOUS_MULTIPLE_SOURCE_SAMPLE_RECORDS"
            granularity="SAME_16_CHAR_SPECIMEN_MULTIPLE"
        else:
            status="SAME_16_CHAR_SPECIMEN_OLD_STUDY_PURITY_REFERENCE"
            granularity="SAME_16_CHAR_SPECIMEN_NOT_RNA_ALIQUOT"
        purity_by_method={}
        for name in ["CPE","ESTIMATE","ABSOLUTE","LUMP","IHC"]:
            vals={numeric(c.get(name)) for c in chosen}
            vals.discard(None)
            purity_by_method[name]="|".join(str(round(x,6)) for x in sorted(vals))
        output.append({
            "patient_id":pid,"rna_sample_barcode":bar,
            "source_sample_barcode":"|".join(sorted({x["source_sample_barcode"] for x in chosen})),
            "match_granularity":granularity,
            "candidate_source_rows":len(chosen),
            "cpe":purity_by_method["CPE"],
            "estimate":purity_by_method["ESTIMATE"],
            "absolute":purity_by_method["ABSOLUTE"],
            "lump":purity_by_method["LUMP"],
            "ihc":purity_by_method["IHC"],
            "published_cancer_type":"|".join(sorted({str(x.get("Cancer.type") or "") for x in chosen})),
            "consensus_purity_status":status,
            "clinical_eligibility":"NOT_ASSESSED",
            "interpretation":"Historical PanCancer consensus/algorithmic estimate, not measured in identical GDC STAR RNA aliquot or pretherapy MRI HCC lesion.",
        })
    return output


def offline_test():
    from zipfile import ZIP_DEFLATED
    # Validate ID join and fail-closed cross-aliquot interpretation independently
    mock=[{"source_sample_barcode":"TCGA-AA-0001-01A","CPE":"0.5",
           "ESTIMATE":"0.6","ABSOLUTE":"0.4","LUMP":"","IHC":""}]
    x=join([{"patient_id":"TCGA-AA-0001","aliquot_barcode":"TCGA-AA-0001-01A-11R-1234-07"}],mock)
    assert x[0]["cpe"]=="0.5"
    assert x[0]["match_granularity"]=="SAME_16_CHAR_SPECIMEN_NOT_RNA_ALIQUOT"
    assert x[0]["clinical_eligibility"]=="NOT_ASSESSED"
    s=["Sample.ID","Cancer.type","ESTIMATE","ABSOLUTE","LUMP","IHC","CPE"]
    assert normalize_header(s[0])=="sampleid"
    print("HCC_ARAN_CPE_CONSENSUS_PURITY_JOIN_OFFLINE_PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--offline-test",action="store_true")
    ap.add_argument("--output",default="artifacts/hcc_cpe")
    args=ap.parse_args()
    if args.offline_test:return offline_test()
    with open(MANIFEST,encoding="utf-8",newline="") as f:
        ids=list(csv.DictReader(f))
    if len(ids)!=14:raise ValueError("Frozen manifest not 14")
    data,url=fetch()
    source,meta=parse_workbook(data)
    out=join(ids,source)
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    with (root/"hcc_mri_14_aran_consensus_purity_crosswalk.csv").open(
            "w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=OUT);w.writeheader();w.writerows(out)
    summary={
        "status":"PASS_HISTORICAL_CPE_CROSSWALK_ONLY",
        "source_url":url,"source_sha256":hashlib.sha256(data).hexdigest(),
        "source_bytes":len(data),
        "source_study":"Aran Sirota Butte Nature Communications 2015 doi:10.1038/ncomms9971",
        "study_worksheet_metadata":[{"worksheet":x["worksheet"],"rows":x["rows"],
             "preview":x["sample_preview"][:1]} for x in meta],
        "n_source_sample_rows":len(source),
        "n_frozen_mri_rna_cases":len(out),
        "sample_match_status_counts":dict(Counter(r["consensus_purity_status"] for r in out)),
        "cpe_available_same_16_char_specimen":sum(
            r["match_granularity"]=="SAME_16_CHAR_SPECIMEN_NOT_RNA_ALIQUOT"
            and bool(r["cpe"]) for r in out),
        "mri_rna_associations_performed":False,
        "clinically_qualified_patient_count":"NOT_ASSESSED",
        "manuscript_claim_ceiling":"S0",
        "note":"Historical CPE may be based on different TCGA RNA assay/reference and is not a direct GDC STAR purity measurement; never promote clinical eligibility."
    }
    (root/"hcc_mri_14_aran_consensus_purity_summary.json").write_text(
        json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
