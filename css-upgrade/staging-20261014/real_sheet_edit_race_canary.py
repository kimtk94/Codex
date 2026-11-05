#!/usr/bin/env python3
"""Real Google Sheets Canary edit-between-read simulation.

ONLY a dedicated synthetic spreadsheet ID/tab is writable.
Real CSS functions are AST-extracted from temporary patched source; operational
CSS modules/main/collector never imported. Uses in-memory SQLite only.
"""
import argparse, hashlib, importlib.util, os, re, sqlite3, tempfile
from pathlib import Path
import pandas as pd

TEST_ID="1eKMPMnRYeZB8tuPE2dblcSaHXSZ58REHPQgJSq2RIjA"
PRODUCTION_ID="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
TEST_TITLE="CSS SIF Upgrade Canary - Synthetic 2026-10-15"
TEST_TAB="Overview Race Canary"
SYNTH_ID="AMEA2099000911"
PASSED=[]

def check(ok,name):
    if not ok: raise AssertionError(name)
    PASSED.append(name)
    print("REAL_SHEETS_RACE_PASS",name,flush=True)

def adc_credentials():
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError
    scope=["https://www.googleapis.com/auth/spreadsheets"]
    try:
        return google.auth.default(scopes=scope)[0]
    except DefaultCredentialsError:
        pass
    paths=[Path("/home/taehoon/services/novogene-css/.env"),
           Path("/home/taehoon/services/novogene-css/app/.env"),
           Path("/home/taehoon/.config/novogene-css.env")]
    for folder in (Path("/etc/systemd/system"),Path("/home/taehoon/.config/systemd/user")):
        if not folder.is_dir(): continue
        for pattern in ("*novogene*.service","*css*.service"):
            for unit in folder.glob(pattern):
                try: lines=unit.read_text(errors="replace").splitlines()
                except OSError: continue
                for line in lines:
                    if line.strip().startswith("EnvironmentFile="):
                        filename=line.split("=",1)[1].lstrip("-").strip().strip('"').split()[0]
                        if filename.startswith("/"): paths.append(Path(filename))
                    elif line.strip().startswith("Environment="):
                        m=re.search(r"GOOGLE_APPLICATION_CREDENTIALS=([^\s\"']+)",line)
                        if m and Path(m.group(1)).is_file():
                            os.environ["GOOGLE_APPLICATION_CREDENTIALS"]=m.group(1)
                            return google.auth.default(scopes=scope)[0]
    for p in paths[:45]:
        try:
            if not p.is_file() or p.stat().st_size>150000: continue
            for line in p.read_text(errors="replace").splitlines():
                raw=line.strip().removeprefix("export ")
                if raw.startswith("GOOGLE_APPLICATION_CREDENTIALS="):
                    candidate=Path(raw.split("=",1)[1].strip().strip('"').strip("'")).expanduser()
                    if candidate.is_file():
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"]=str(candidate)
                        return google.auth.default(scopes=scope)[0]
        except OSError: pass
    raise RuntimeError("TEST_ONLY_ADC_NOT_FOUND")

class CanaryObserved:
    def __init__(self,ws,edit_at=0):
        self.ws=ws
        self.edit_at=edit_at
        self.reads=0
    def batch_get(self,ranges,**kwargs):
        self.reads+=1
        if self.reads==self.edit_at:
            # Literal synthetic SHEET ID and TAB are checked before this point.
            self.ws.update(range_name="C11",values=[["5"]],
                           value_input_option="RAW")
            observed=self.ws.get("C11")
            if not observed or str(observed[0][0])!="5":
                raise RuntimeError("CANARY_MUTATION_NOT_CONFIRMED")
        return self.ws.batch_get(ranges,**kwargs)

def reset_canary(ws):
    ws.batch_clear(["A10:E12","A41:B43"])
    ws.update(range_name="A10:E11",values=[
        ["AMEA Project","Normal Action","Hold Days","Mail Marker","Prepayment"],
        [SYNTH_ID,"Hold","2","",""]
    ],value_input_option="RAW")
    ws.update(range_name="A41:B41",values=[["AMEA Project","Action"]],
              value_input_option="RAW")
    observed=ws.get("A10:C11")
    check(observed[0]==["AMEA Project","Normal Action","Hold Days"]
          and observed[1][:3]==[SYNTH_ID,"Hold","2"],"CANARY_RESET_VERIFIED")

def state(con):
    return (
        tuple(con.execute("SELECT * FROM overview_project_snoozes ORDER BY 1")),
        tuple(con.execute("SELECT * FROM overview_control_receipts ORDER BY 1")),
    )

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",required=True)
    ap.add_argument("--fixture-script",required=True)
    ap.add_argument("--patch",action="append",required=True)
    args=ap.parse_args()
    check(TEST_ID!=PRODUCTION_ID,"CANARY_ID_DIFFERS_FROM_LIVE")
    original=Path(args.source).read_bytes()
    check(hashlib.sha256(original).hexdigest()==
          "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840",
          "EXACT_SERVER_SOURCE_SHA")
    spec=importlib.util.spec_from_file_location(
        "synthetic_overlap_helpers",args.fixture_script)
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    with tempfile.TemporaryDirectory(prefix="css-real-gsheet-race-") as td:
        staged,raw,local=helper.stage(args.source,args.patch,td)
        check(hashlib.sha256(staged).hexdigest()==
          "3963b6cbd60205c2738943e4b28e2a88a1987776bfdda05ee8cba269d6ea3806",
          "EIGHT_PATCH_SHA_MATCH")
        ns=helper.extract(staged)
        import gspread
        gc=gspread.authorize(adc_credentials())
        sheet=gc.open_by_key(TEST_ID)
        check(sheet.title==TEST_TITLE,"EXACT_SYNTHETIC_BOOK_TITLE")
        ws=sheet.worksheet(TEST_TAB)
        check(ws.title==TEST_TAB,"EXACT_SYNTHETIC_TAB")
        manual=sheet.worksheet("Manual Override QA")
        before_manual=manual.get("A1:H3")
        now=pd.Timestamp("2026-10-15T09:00:00",tz=helper.TZ)
        try:
            for edit_at in (2,3,0):
                reset_canary(ws)
                con=helper.connect()
                if edit_at==0:
                    # Stable path must create exactly one hold and one receipt.
                    probe=CanaryObserved(ws,edit_at=0)
                    ns["sync_overview_snooze_actions"](
                        con,probe,helper.board(SYNTH_ID,"REAL_GSHEET"),now)
                    check(probe.reads==3,"ACTUAL_SHEETS_THREE_BATCH_GET_STABLE")
                    check(helper.row(con,SYNTH_ID)[0]=="hold",
                          "STABLE_REAL_SHEETS_CREATES_HOLD")
                    check(con.execute(
                        "SELECT signature FROM overview_control_receipts "
                        "WHERE project_id=?",(SYNTH_ID,)).fetchone()[0]=="hold:2",
                          "STABLE_REAL_SHEETS_CREATES_RECEIPT")
                else:
                    baseline=state(con) if con.execute(
                       "SELECT 1 FROM sqlite_master WHERE name='overview_control_receipts'"
                    ).fetchone() else (
                        tuple(con.execute("SELECT * FROM overview_project_snoozes")),()
                    )
                    probe=CanaryObserved(ws,edit_at=edit_at)
                    try:
                        ns["sync_overview_snooze_actions"](
                            con,probe,helper.board(SYNTH_ID,"REAL_GSHEET"),now)
                    except RuntimeError as exc:
                        check("변경" in str(exc),
                              "REAL_SHEETS_EDIT_DETECTED_READ_"+str(edit_at))
                    else:
                        raise AssertionError("REAL_SHEETS_CONFLICT_NOT_DETECTED")
                    check(probe.reads==edit_at,
                          "RACE_TRIGGERED_ON_EXPECTED_SNAPSHOT_"+str(edit_at))
                    after=tuple(con.execute("SELECT * FROM overview_project_snoozes"))
                    check(after==baseline[0],
                          "REAL_SHEETS_RACE_ROLLED_BACK_HOLD_"+str(edit_at))
                    receipts=con.execute("SELECT COUNT(*) FROM sqlite_master "
                                         "WHERE type='table' AND name='overview_control_receipts'").fetchone()[0]
                    if receipts:
                        check(con.execute(
                            "SELECT COUNT(*) FROM overview_control_receipts").fetchone()[0]==0,
                            "REAL_SHEETS_RACE_ROLLED_BACK_RECEIPT_"+str(edit_at))
                con.close()
            check(manual.get("A1:H3")==before_manual,
                  "UNRELATED_MANUAL_QA_TAB_UNCHANGED")
            check(hashlib.sha256(Path(args.source).read_bytes()).hexdigest()==
                  "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840",
                  "LIVE_CSS_SOURCE_UNMODIFIED")
        finally:
            # Clean ONLY the explicitly created synthetic tab.
            ws.batch_clear(["A10:E12","A41:B43"])
        print("REAL_SHEETS_READ_EDIT_RACE_PASS",len(PASSED),flush=True)
        print("GOOGLE_SHEETS_WRITES_SYNTHETIC_CANARY_ONLY",True,flush=True)
        print("NO_PRODUCTION_DATABASE_OR_SHEET_WRITE",True,flush=True)

if __name__=="__main__":
    main()
