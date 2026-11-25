#!/usr/bin/env python3
"""Historical archive/handoff integrity only; never a prospective seal.

No credentials, networking, Drive writes, market price certification, or trading.
The GitHub metadata is supplied by a read-only Actions step. A private external
receipt and separately downloaded Drive ZIPs are optional. Do not commit them.
A saved receipt alone is not a fresh independent Drive readback.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

VERSION = "kalman-challenger-archive-audit-v1"
REPO_ID = 1201389408
CUTOFF = "2026-11-23"
PROTOCOL = "e72ad78b04e5667539f50cd8076e578c9b20ae36e3549c22b543e2fb91b2f93d"
PINS = {
    "source_data": dict(id=14914498151, run=45383657032,
        name="kalman-daily20-data", size=9435424, members=52,
        sha="6b5cec11a98fd160496d476ff7f773a3be8ecdaf49867cadadef9d20da6d36cf",
        commit="814b1bc79e18c240275205571d8252fbfed10769"),
    "source_research": dict(id=14915426739, run=45383657032,
        name="kalman-daily20-research", size=13084495, members=135,
        sha="c6e711b7db3f91d5081947f95b320fe3cbbddfeb671df97edf9a24a4ff5f2d6f",
        commit="814b1bc79e18c240275205571d8252fbfed10769"),
    "historical_rehearsal": dict(id=14926365571, run=45405801229,
        name="challenger-historical-rehearsal-not-forward", size=1520, members=1,
        sha="0e6a6e8f1a60aba975d09a1aa8bcb925252f8a947f1a028f70804191fecde53c",
        commit="a4a619bd5d803443b0dcb57b853daffbc5d2c4ef"),
}


def require(ok, code):
    if not ok:
        raise ValueError("ARCHIVE_"+code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(items):
        out = {}
        for k,v in items:
            require(k not in out,"DUPLICATE_JSON_KEY")
            out[k]=v
        return out
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))


def stamp(s):
    t=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(t.tzinfo is not None,"TIMEZONE_REQUIRED")
    return t.astimezone(timezone.utc)


def sha_ok(s):
    return isinstance(s,str) and re.fullmatch("[a-f0-9]{64}",s) is not None


def verify_metadata(meta,pin):
    run=meta["workflow_run"]
    require(type(meta["id"]) is int and meta["id"]==pin["id"]
            and meta["name"]==pin["name"] and meta["size_in_bytes"]==pin["size"]
            and meta["digest"]=="sha256:"+pin["sha"]
            and run["id"]==pin["run"] and run["head_sha"]==pin["commit"]
            and run["repository_id"]==run["head_repository_id"]==REPO_ID
            and meta["expired"] is False,"GITHUB_METADATA_MISMATCH")
    require(stamp(meta["created_at"])<stamp(meta["expires_at"]),"METADATA_TIME")
    return dict(created_at=meta["created_at"],expires_at=meta["expires_at"])


def verify_zip(raw,pin):
    require(len(raw)==pin["size"] and sha(raw)==pin["sha"],"ZIP_SHA_OR_SIZE")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        require(len(names)==len(set(names))==pin["members"],"ZIP_MEMBER_COUNT")
        require(all(n and not n.startswith("/") and "\\" not in n
                    and ".." not in PurePosixPath(n).parts
                    and not re.match(r"^[A-Za-z]:",n)
                    and not i.is_dir()
                    and (i.external_attr>>16)&0o170000!=0o120000
                    for n,i in zip(names,z.infolist())),"ZIP_UNSAFE_PATH")
        require(sum(i.file_size for i in z.infolist())<=512*1024*1024,
                "ZIP_EXPANSION_LIMIT")
        require(z.testzip() is None,"ZIP_CRC")
        return set(names)


def inspect_historical(role,raw,pin):
    names=verify_zip(raw,pin)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if role=="source_data":
            require(sum(n.startswith("market/raw/yfinance/") and n.endswith(".parquet")
                        for n in names)==26
                    and sum(n.startswith("features/talib/") and n.endswith(".parquet")
                            for n in names)==26,"DATA_26_PLUS_26")
        elif role=="source_research":
            q=parse(z.read("qc.json"))
            require(q["expected_session"]==CUTOFF and q["status"]=="READY"
                    and q["required"]==q["ready"]==26
                    and q["research_only"] is True,"RESEARCH_QC_CUTOFF")
        elif role=="historical_rehearsal":
            require(names=={"historical_rehearsal.json"},"REHEARSAL_MEMBER")
            r=parse(z.read("historical_rehearsal.json"))
            require(r["status"]=="HISTORICAL_REHEARSAL_NOT_FORWARD"
                    and r["research_only"] is True and r["approved_live"] is False
                    and r["source_finality_certified"] is False
                    and r["forward_signals_created"]==0
                    and r["protocol_sha256"]==PROTOCOL
                    and r["first_session"]=="2024-01-02" and r["last_session"]==CUTOFF
                    and r["sessions"]==727 and len(r["scenarios"])==12
                    and r["source_data_sha256"]==PINS["source_data"]["sha"]
                    and r["source_research_sha256"]==PINS["source_research"]["sha"],
                    "REHEARSAL_SCOPE_OR_PROVENANCE")
        else:
            raise ValueError("UNKNOWN_HISTORICAL_ROLE")
    return dict(role=role,artifact_id=pin["id"],run_id=pin["run"],
                sha256=pin["sha"],bytes=pin["size"],members=pin["members"],crc_pass=True)


def verify_receipt(raw,expected):
    require(sha_ok(expected) and sha(raw)==expected,"RECEIPT_HASH_MISMATCH")
    r=parse(raw)
    require(r["version"]=="kalman-challenger-archive-receipt-v1"
            and r["status"]=="ARCHIVE_READBACK_PASS_NOT_FORWARD"
            and r["drive_account"]=="Taehoon"
            and r["research_cutoff"]==CUTOFF and r["protocol_sha256"]==PROTOCOL
            and r["research_only"] is True and r["approved_live"] is False
            and r["source_finality_certified"] is False
            and r["forward_signals_created"]==0,"RECEIPT_SCOPE")
    rows=r["files"]
    require(len(rows)==3 and {v["role"] for v in rows}==set(PINS)
            and len({v["drive_file_id"] for v in rows})==3
            and len({v["name"] for v in rows})==3,"RECEIPT_INVENTORY")
    require(isinstance(r["drive_folder_id"],str) and bool(r["drive_folder_id"]),
            "RECEIPT_FOLDER")
    for row in rows:
        p=PINS[row["role"]]
        require(row["artifact_id"]==p["id"] and row["run_id"]==p["run"]
                and row["bytes"]==p["size"] and row["zip_member_count"]==p["members"]
                and row["github_sha256"]==row["drive_readback_sha256"]==p["sha"]
                and row["crc_pass"] is True and bool(row["drive_file_id"])
                and stamp(row["drive_created_utc"])<=stamp(row["drive_modified_utc"]),
                "RECEIPT_FILE_MISMATCH")
        name=row["name"]
        require(isinstance(name,str) and name.endswith(".zip") and Path(name).name==name
                and "\\" not in name,"RECEIPT_LOCAL_PATH")
    return {v["role"]:v for v in rows}


def audit(github_dir=None,meta_dir=None,receipt=None,receipt_sha=None,drive_dir=None):
    require(github_dir is not None or drive_dir is not None,"NO_ARCHIVE_INPUT")
    require((github_dir is None)==(meta_dir is None),"METADATA_INPUT_PAIR")
    require((receipt is None)==(receipt_sha is None),"RECEIPT_INPUT_PAIR")
    require(drive_dir is None or receipt is not None,"DRIVE_REQUIRES_PINNED_RECEIPT")
    rows=verify_receipt(Path(receipt).read_bytes(),receipt_sha) if receipt else None
    report=[]
    for role,p in PINS.items():
        record=None
        if github_dir:
            meta=parse((Path(meta_dir)/(role+".json")).read_bytes())
            dates=verify_metadata(meta,p)
            raw=(Path(github_dir)/(role+".zip")).read_bytes()
            record=inspect_historical(role,raw,p)
            record.update(github_metadata_verified=True,**dates)
        if drive_dir:
            # Caller must independently authenticate/download these copies.
            raw=(Path(drive_dir)/rows[role]["name"]).read_bytes()
            record=record or inspect_historical(role,raw,p)
            inspect_historical(role,raw,p)
            record["drive_supplied_copy_matches_pin"]=True
        record.setdefault("github_metadata_verified",False)
        record.setdefault("drive_supplied_copy_matches_pin",False)
        report.append(record)
    return dict(version=VERSION,
        status="HISTORICAL_ARCHIVE_BYTES_VERIFIED_NOT_FORWARD",
        repository="kimtk94/Codex",research_cutoff=CUTOFF,protocol_sha256=PROTOCOL,
        research_only=True,approved_live=False,source_finality_certified=False,
        forward_signals_created=0,authenticated_drive_origin_by_this_cli=False,
        private_receipt_hash_verified=bool(rows),
        mode=("DUAL_SUPPLIED_COPIES" if github_dir and drive_dir else
              "DRIVE_RECOVERY_COPY_ONLY" if drive_dir else "GITHUB_ONLY"),
        files=report,limitations=[
            "Supplied Drive bytes can be checked, but provider origin/permissions are external.",
            "A saved receipt is not a fresh Drive readback.",
            "No prospective activation or timestamp attestation.",
            "Artifact expiry is not repaired by this verifier. Restore a pinned copy explicitly."])


def prepare_handoff(report,meta,artifact_zip,expected_run,expected_commit):
    raw=Path(report).read_bytes()
    r=parse(raw)
    require(r["status"]=="HISTORICAL_REHEARSAL_NOT_FORWARD"
            and r["research_only"] is True and r["approved_live"] is False
            and r["source_finality_certified"] is False
            and r["forward_signals_created"]==0
            and r["protocol_sha256"]==PROTOCOL and r["last_session"]==CUTOFF
            and r["sessions"]==727 and len(r["scenarios"])==12
            and r["source_data_sha256"]==PINS["source_data"]["sha"]
            and r["source_research_sha256"]==PINS["source_research"]["sha"],
            "HANDOFF_REPORT_NOT_HISTORICAL")
    run=meta["workflow_run"]
    require(type(meta["id"]) is int and meta["id"]>0
            and meta["name"]==PINS["historical_rehearsal"]["name"]
            and meta["expired"] is False and meta["size_in_bytes"]>0
            and meta["digest"].startswith("sha256:")
            and sha_ok(meta["digest"][7:])
            and run["id"]==expected_run and run["head_sha"]==expected_commit
            and run["repository_id"]==run["head_repository_id"]==REPO_ID,
            "HANDOFF_METADATA_MISMATCH")
    require(stamp(meta["created_at"])<stamp(meta["expires_at"]),"HANDOFF_METADATA_TIME")
    zipped=Path(artifact_zip).read_bytes()
    names=verify_zip(zipped,dict(size=meta["size_in_bytes"],sha=meta["digest"][7:],members=1))
    require(names=={"historical_rehearsal.json"},"HANDOFF_ZIP_MEMBER")
    with zipfile.ZipFile(io.BytesIO(zipped)) as z:
        require(z.read("historical_rehearsal.json")==raw,"HANDOFF_REPORT_BYTES")
    return dict(version="kalman-challenger-historical-handoff-v1",
                status="AWAITING_INDEPENDENT_ARCHIVE_COPY_NOT_FORWARD",
                research_only=True,approved_live=False,source_finality_certified=False,
                forward_signals_created=0,protocol_sha256=PROTOCOL,research_cutoff=CUTOFF,
                artifact_id=meta["id"],run_id=run["id"],commit=run["head_sha"],
                artifact_sha256=meta["digest"][7:],artifact_bytes=meta["size_in_bytes"],
                report_sha256=sha(raw),created_at=meta["created_at"],
                expires_at=meta["expires_at"],drive_storage_verified=False)


def write_new(path,result):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x") as f:
        f.write(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+"\n")


def self_test():
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("a.json","{}")
    raw=buf.getvalue()
    pin=dict(size=len(raw),sha=sha(raw),members=1,id=1,run=2,name="test",commit="a"*40)
    require(verify_zip(raw,pin)=={"a.json"},"TEST_VALID_ZIP")
    def reject(fn,code):
        try:
            fn()
        except ValueError as e:
            require(str(e)=="ARCHIVE_"+code,"TEST_WRONG_REJECTION")
        else:
            raise AssertionError("EXPECTED_REJECTION:"+code)
    reject(lambda:verify_zip(raw+b"x",pin),"ZIP_SHA_OR_SIZE")
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("../bad","x")
    unsafe=buf.getvalue()
    reject(lambda:verify_zip(unsafe,dict(pin,size=len(unsafe),sha=sha(unsafe))),
           "ZIP_UNSAFE_PATH")
    m=dict(id=1,name="test",size_in_bytes=len(raw),digest="sha256:"+sha(raw),
           expired=False,created_at="2026-11-24T00:00:00Z",expires_at="2026-12-15T00:00:00Z",
           workflow_run=dict(id=2,head_sha="a"*40,repository_id=REPO_ID,
                             head_repository_id=REPO_ID))
    verify_metadata(m,pin)
    reject(lambda:verify_metadata(dict(m,expired=True),pin),"GITHUB_METADATA_MISMATCH")
    reject(lambda:verify_metadata(dict(m,digest="sha256:"+"0"*64),pin),"GITHUB_METADATA_MISMATCH")
    reject(lambda:verify_receipt(b"{}","0"*64),"RECEIPT_HASH_MISMATCH")
    reject(lambda:audit(drive_dir="fake"),"DRIVE_REQUIRES_PINNED_RECEIPT")
    with tempfile.TemporaryDirectory() as t:
        path=Path(t)/"report.json"
        write_new(path,{"test":True})
        try:
            write_new(path,{"test":False})
        except FileExistsError:
            pass
        else:
            raise AssertionError("OUTPUT_OVERWRITTEN")
    print("CHALLENGER_ARCHIVE_CONTRACT_PASS")


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--self-test",action="store_true")
    for k in ("github-dir","meta-dir","receipt","receipt-sha256","drive-dir","out",
              "handoff-report","handoff-meta","handoff-zip","expected-commit"):
        a.add_argument("--"+k)
    a.add_argument("--expected-run",type=int)
    x=a.parse_args()
    if x.self_test:
        self_test()
        return
    require(x.out,"OUTPUT_REQUIRED")
    if x.handoff_report:
        require(x.handoff_meta and x.handoff_zip and x.expected_commit and x.expected_run,
                "HANDOFF_INPUTS_REQUIRED")
        result=prepare_handoff(x.handoff_report,parse(Path(x.handoff_meta).read_bytes()),
                               x.handoff_zip,x.expected_run,x.expected_commit)
    else:
        result=audit(x.github_dir,x.meta_dir,x.receipt,x.receipt_sha256,x.drive_dir)
    write_new(x.out,result)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
