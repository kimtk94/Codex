#!/usr/bin/env python3
"""Read-only lineage quarantine for Unissued Invoice Watch project contracts.

A Watch H/X identifier is NOT an allowed join key unless Feishu corroborates
the same AMEA. Cross-customer links and missing IDs are never auto-corrected.
Writes only the generated 'CSS Unissued Contract Lineage Review' tab.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import quote
from zoneinfo import ZoneInfo

BOOK="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB="CSS Unissued Contract Lineage Review"
KST=ZoneInfo("Asia/Seoul")
HEAD=["AMEA","Watch Project / Institution","Watch H Contract","Watch X Sub-project",
      "Watch Quote KRW","Feishu X Base Key","Feishu Referenced AMEA",
      "Outstanding Evidence Rows","eTax Evidence Rows","Source Effective Date",
      "Link Verification State","Contract Attribution Decision",
      "Review Instruction","Checked KST","GitHub Run"]
X_VALID=re.compile(r"^X[A-Z0-9]{10,30}(?:-Z\d{2}(?:-F\d{3})?)?$",re.I)
AMEA_VALID=re.compile(r"^AMEA20\d{8}$")

def cell(row,index):
    return str(row[index]).strip() if row is not None and index<len(row) and row[index] is not None else ""

def normalized_x(value):
    key=value.strip().upper()
    if not key:return ""
    if not X_VALID.fullmatch(key):return ""
    return key.split("-Z",1)[0]

def classify_watch_formula_provenance(project_formula,contract_formula):
    """Never treat independently FILTER-spilled forecast and contract rows as a join."""
    project=str(project_formula or "").strip()
    contract=str(contract_formula or "").strip()
    if not (project.startswith("=") and contract.startswith("=")):
        return "WATCH_FORMULA_PROVENANCE_UNKNOWN"
    if (re.search(r"\bFILTER\s*\(",project,re.I)
        and re.search(r"\bFILTER\s*\(",contract,re.I)
        and "'BI 2026 Completion Forecast'" in project
        and "'BI Revenue Duplicate Review'" in contract
        and not re.search(r"\b(?:XLOOKUP|VLOOKUP|MATCH|INDEX|QUERY)\s*\(",contract,re.I)
        and not re.search(r"\bAMEA\b",contract,re.I)):
        return "POSITIONAL_INDEPENDENT_FILTER_CONFIRMED"
    # A rewritten formula is not approved until its actual AMEA-keyed mapping is audited.
    return "WATCH_FORMULA_REQUIRES_KEYED_REVIEW"


def verify(watch,outstanding,etax,manifest,now):
    if now.tzinfo is None:raise ValueError("NAIVE_CLOCK")
    if not watch or [cell(watch[0],i) for i in (0,4,6,10,12,13)] != [
        "AMEA Project ID","Quote KRW","Matched Invoice Count",
        "Review Status","H Contract","X Sub-project"]:
        raise ValueError("WATCH_SCHEMA_CHANGED")
    if not outstanding or [cell(outstanding[0],i) for i in (5,7,12,13)] != [
        "Project Number","Quotation Number","Invoice Amount","Balance"]:
        raise ValueError("OUTSTANDING_SCHEMA_CHANGED")
    if not etax or [cell(etax[0],i) for i in (9,10,15)] != [
        "Project Number","Quotation Number","Amount"]:
        raise ValueError("ETAX_SCHEMA_CHANGED")
    if not manifest or [cell(manifest[0],i) for i in (0,1,4)] != [
        "Source","Source Date","Rows"]:
        raise ValueError("FEISHU_SOURCE_MANIFEST_CHANGED")
    if len(watch)<2:raise ValueError("WATCH_NO_PROJECT_ROWS")
    snapshot={}
    for source in ("Payment Outstanding","eTax Invoice"):
        found=[r for r in manifest[1:] if cell(r,0)==source]
        if len(found)!=1:raise ValueError("SOURCE_MISSING_"+source)
        try:
            day=dt.date.fromisoformat(cell(found[0],1))
            expected=int(cell(found[0],4))
        except (ValueError,TypeError) as e:raise ValueError("SOURCE_MANIFEST_INVALID_"+source) from e
        if day>now.astimezone(KST).date():raise ValueError("FUTURE_SOURCE_DATE")
        snapshot[source]=(day,expected)
    if snapshot["Payment Outstanding"][1]!=len(outstanding)-1:
        raise ValueError("OUTSTANDING_MIRROR_ROW_DRIFT")
    if snapshot["eTax Invoice"][1]!=len(etax)-1:
        raise ValueError("ETAX_MIRROR_ROW_DRIFT")
    group=collections.defaultdict(lambda:{"out":[],"tax":[]})
    for name,data,x_col,amea_col,field in (
        ("outstanding",outstanding,5,7,"out"),
        ("etax",etax,9,10,"tax")):
        for record in data[1:]:
            raw_x=cell(record,x_col)
            if not raw_x:continue
            x=normalized_x(raw_x)
            if not x:raise ValueError("FEISHU_X_FORMAT_INVALID_"+name)
            amea=cell(record,amea_col)
            if not AMEA_VALID.fullmatch(amea):
                # A row without a verifiable AMEA is not negative match proof.
                group[x][field].append("")
            else:group[x][field].append(amea)
    reviewed=[]
    seen_watch=set()
    for record in watch[1:]:
        amea=cell(record,0)
        if not amea:continue
        if not AMEA_VALID.fullmatch(amea):raise ValueError("WATCH_AMEA_INVALID")
        if amea in seen_watch:raise ValueError("WATCH_DUPLICATE_AMEA")
        seen_watch.add(amea)
        if cell(record,10)!="ISSUANCE_NOT_VERIFIED":
            raise ValueError("WATCH_APPROVAL_WAS_CHANGED")
        raw_x=cell(record,13)
        x=normalized_x(raw_x)
        if raw_x and not x:
            state="INVALID_WATCH_X_FORMAT"
        elif not x:
            state="MISSING_WATCH_X"
        else:
            origin=group.get(x)
            if not origin:
                state="X_NOT_IN_FEISHU_SNAPSHOT"
            else:
                all_found=origin["out"]+origin["tax"]
                verified={a for a in all_found if a}
                if not verified:
                    state="X_PRESENT_BUT_AMEA_NOT_VERIFIED"
                elif amea in verified and len(verified)==1 and "" not in all_found:
                    state="X_MATCHED_SAME_AMEA_ON_STALE_SNAPSHOT"
                elif amea in verified:
                    state="X_AMBIGUOUS_MULTIPLE_AMEAS"
                elif len(verified)==1 and "" not in all_found:
                    state="X_REFERENCES_DIFFERENT_AMEA"
                else:
                    state="X_REFERENCES_MULTIPLE_OR_UNKNOWN_AMEAS"
        refs=group.get(x,{"out":[],"tax":[]}) if x else {"out":[],"tax":[]}
        names=sorted({v for v in refs["out"]+refs["tax"] if v})
        confidence="SNAPSHOT_LINK_ONLY_NOT_ISSUANCE" if state=="X_MATCHED_SAME_AMEA_ON_STALE_SNAPSHOT" else "QUARANTINE_CONTRACT_ATTRIBUTION"
        message=(
           "Do not join by Watch H/X. Cross-check project AMEA and original contract/Invoice PDF; "
           "do not book Forecast as Actual or certify issued/paid.")
        reviewed.append([amea,cell(record,1),cell(record,12),raw_x,
            cell(record,4),x," | ".join(names),len(refs["out"]),len(refs["tax"]),
            snapshot["eTax Invoice"][0].isoformat(),state,confidence,message,
            now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST"),""])
    if not reviewed:raise ValueError("WATCH_VALIDATED_ROWS_EMPTY")
    stats=dict(collections.Counter(row[10] for row in reviewed))
    return reviewed,{"watch_projects":len(reviewed),"states":dict(sorted(stats.items())),
        "foreign_amea_links":stats.get("X_REFERENCES_DIFFERENT_AMEA",0),
        "source_effective_date":snapshot["eTax Invoice"][0].isoformat(),
        "source_age_days":(now.astimezone(KST).date()-snapshot["eTax Invoice"][0]).days,
        "business_source_writes":0,"issuance_or_payment_certified":0}

def main():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    token=os.getenv("CKD_DRIVE_SA_JSON","")
    run=os.getenv("GITHUB_RUN_ID","")
    if not token or not run.isdigit() or os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex":
        raise RuntimeError("UNTRUSTED_GITHUB_CONTEXT")
    credential=service_account.Credentials.from_service_account_info(
        json.loads(token),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    http=AuthorizedSession(credential)
    root="https://sheets.googleapis.com/v4/spreadsheets/"+BOOK
    def req(method,url,**kwargs):
        res=http.request(method,url,timeout=60,**kwargs)
        res.raise_for_status()
        return res.json() if res.content else {}
    def read(name,rng):
        return req("GET",root+"/values/"+quote("'"+name+"'!"+rng,safe="")).get("values",[])
    rows,summary=verify(
        read("Unissued Invoice Watch","A1:O500"),
        read("Feishu Latest Outstanding","A1:Q350"),
        read("Feishu Latest eTax","A1:AI200"),
        read("Feishu Source Manifest","A1:G15"),
        dt.datetime.now(KST))
    def formula_of(a1):
        data=req("GET",root+"/values/"+quote("'Unissued Invoice Watch'!"+a1,safe=""),
                 params={"valueRenderOption":"FORMULA"}).get("values",[])
        return cell(data[0],0) if data else ""
    formula_state=classify_watch_formula_provenance(formula_of("A2"),formula_of("M2"))
    summary["watch_contract_formula_provenance"]=formula_state
    summary["watch_contract_join_approved"]=False
    for row in rows:
        # Even accidental AMEA parity cannot validate a positional source formula.
        row[11]="QUARANTINE_CONTRACT_ATTRIBUTION"
        row[12]+=" Contract formula provenance: "+formula_state+"; never join independent row positions."
    metadata=req("GET",root,params={"fields":"sheets.properties(title,sheetId)"})
    if not any(item.get("properties",{}).get("title")==TAB for item in metadata.get("sheets",[])):
        req("POST",root+":batchUpdate",json={"requests":[{"addSheet":{
            "properties":{"title":TAB,"gridProperties":{
                "rowCount":600,"columnCount":len(HEAD),"frozenRowCount":1}}}}]})
    output=[HEAD]+[r[:-1]+["https://github.com/kimtk94/Codex/actions/runs/"+run] for r in rows]
    path=root+"/values/"+quote("'"+TAB+"'!A1:O"+str(len(output)),safe="")
    old=req("GET",path).get("values",[])
    if old and old[0]!=HEAD:raise RuntimeError("FOREIGN_REVIEW_TAB_NOT_WRITABLE")
    req("POST",root+"/values/"+quote("'"+TAB+"'!A1:O600",safe="")+":clear",json={})
    req("PUT",path,params={"valueInputOption":"RAW"},json={"values":output})
    actual=req("GET",path).get("values",[])
    if actual!=[[str(v) for v in row] for row in output]:
        raise RuntimeError("CONTRACT_LINEAGE_READBACK_FAILURE")
    print("CSS_UNISSUED_CONTRACT_LINEAGE="+json.dumps(summary,sort_keys=True))
    print("NO_CONTRACT_AUTO_FIX;NO_APPROVAL_OR_REVENUE_CHANGE;QUARANTINE_FOREIGN_LINKS")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CSS_UNISSUED_CONTRACT_GUARD_FAILED="+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
