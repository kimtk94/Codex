#!/usr/bin/env python3
"""Create-only historical archive worker for an independently trusted private host.

Never run a credentialed invocation on public PR/Actions runners. No secret
provisioning, sharing changes, scheduler, prospective activation, or live use.
The private operator supplies independently verified GitHub artifact hashes and
an authorized-user OAuth credential limited to drive.file. The selected folder
and any existing archive files must be authorized to that app. One worker/state
directory only; Drive names are not globally unique. Not WORM storage.
"""
import argparse
import fcntl
import io
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

from challenger_archive_audit import (
    CUTOFF, PINS, PROTOCOL, parse, require, sha, sha_ok, stamp, verify_zip,
)

SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER_NAME = "Challenger_Forward_Research_Archives"
FIELDS = ("id,name,mimeType,parents,ownedByMe,shared,trashed,driveId,"
          "size,sha256Checksum,createdTime,modifiedTime,capabilities(canAddChildren)")


def pinned(path, expected, limit=8*1024*1024):
    p = Path(path)
    require(p.is_file() and p.stat().st_size <= limit, "WORKER_INPUT_SIZE")
    raw = p.read_bytes()
    require(sha_ok(expected) and sha(raw)==expected,"WORKER_INPUT_HASH")
    return raw


def inputs(handoff_path, handoff_sha, report_path, report_sha, run, commit):
    require(type(run) is int and run>0 and re.fullmatch("[a-f0-9]{40}",commit),
            "WORKER_RUN_OR_COMMIT")
    h = pinned(handoff_path,handoff_sha)
    r = pinned(report_path,report_sha)
    members = verify_zip(h,dict(size=len(h),sha=handoff_sha,members=2))
    require(members=={"archive_handoff.json","github_archive_audit.json"},
            "WORKER_HANDOFF_MEMBERS")
    with zipfile.ZipFile(io.BytesIO(h)) as z:
        x = parse(z.read("archive_handoff.json"))
        a = parse(z.read("github_archive_audit.json"))
    require(x["version"]=="kalman-challenger-historical-handoff-v1"
            and x["status"]=="AWAITING_INDEPENDENT_ARCHIVE_COPY_NOT_FORWARD"
            and x["drive_storage_verified"] is False
            and x["run_id"]==run and x["commit"]==commit
            and x["artifact_sha256"]==report_sha and x["artifact_bytes"]==len(r)
            and type(x["artifact_id"]) is int and x["artifact_id"]>0
            and stamp(x["created_at"])<stamp(x["expires_at"]),
            "WORKER_HANDOFF_LINK")
    require(a["status"]=="HISTORICAL_ARCHIVE_BYTES_VERIFIED_NOT_FORWARD"
            and a["mode"]=="GITHUB_ONLY" and len(a["files"])==3
            and {v["role"] for v in a["files"]}==set(PINS),
            "WORKER_ORIGINAL_AUDIT")
    for row in a["files"]:
        p=PINS[row["role"]]
        require(row["artifact_id"]==p["id"] and row["run_id"]==p["run"]
                and row["sha256"]==p["sha"] and row["bytes"]==p["size"]
                and row["members"]==p["members"] and row["crc_pass"] is True
                and row["github_metadata_verified"] is True,"WORKER_ORIGINAL_PIN")
    require(verify_zip(r,dict(size=len(r),sha=report_sha,members=1))==
            {"historical_rehearsal.json"},"WORKER_REPORT_MEMBER")
    with zipfile.ZipFile(io.BytesIO(r)) as z:
        raw=z.read("historical_rehearsal.json")
        y=parse(raw)
    require(sha(raw)==x["report_sha256"] and y["status"]=="HISTORICAL_REHEARSAL_NOT_FORWARD"
            and y["sessions"]==727 and len(y["scenarios"])==12
            and y["last_session"]==CUTOFF
            and y["source_data_sha256"]==PINS["source_data"]["sha"]
            and y["source_research_sha256"]==PINS["source_research"]["sha"],
            "WORKER_REPORT_PROVENANCE")
    for d in (a,x,y):
        require(d["research_only"] is True and d["approved_live"] is False
                and d["source_finality_certified"] is False
                and d["forward_signals_created"]==0 and d["protocol_sha256"]==PROTOCOL,
                "WORKER_NOT_HISTORICAL")
    return [
        dict(role="historical_rehearsal",name=f"challenger-worker-GH{run}-{report_sha}.zip",
             sha256=report_sha,raw=r),
        dict(role="archive_audit_handoff",name=f"challenger-worker-GH{run}-{handoff_sha}.zip",
             sha256=handoff_sha,raw=h),
    ]


def identity(service,c):
    user=service.about().get(fields="user(permissionId,emailAddress)").execute()["user"]
    require(user["permissionId"]==c["account_permission_id"]
            and user["emailAddress"].lower()==c["account_email"].lower(),
            "WORKER_WRONG_ACCOUNT")
    folder=service.files().get(fileId=c["folder_id"],fields=FIELDS,
                               supportsAllDrives=True).execute()
    require(folder["id"]==c["folder_id"] and folder["name"]==FOLDER_NAME
            and folder["mimeType"]=="application/vnd.google-apps.folder"
            and folder["parents"]==[c["parent_id"]] and folder["ownedByMe"] is True
            and folder["shared"] is False and folder["trashed"] is False
            and not folder.get("driveId") and folder["capabilities"]["canAddChildren"] is True,
            "WORKER_FOLDER_SCOPE")
    owner_only(service,c["folder_id"],c)


def owner_only(service,file_id,c):
    page=None
    permissions=[]
    while True:
        r=service.permissions().list(fileId=file_id,fields="nextPageToken,permissions(id,type,role)",
            pageSize=100,pageToken=page,supportsAllDrives=True).execute()
        permissions.extend(r["permissions"])
        page=r.get("nextPageToken")
        if not page:
            break
    require(len(permissions)==1 and permissions[0]["id"]==c["account_permission_id"]
            and permissions[0]["type"]=="user" and permissions[0]["role"]=="owner",
            "WORKER_PERMISSION_NOT_OWNER_ONLY")


def list_matches(service,c,name):
    require(re.fullmatch("[A-Za-z0-9_-]+",c["folder_id"]) and
            re.fullmatch("[A-Za-z0-9_.-]+",name),"WORKER_QUERY_SCOPE")
    q=f"'{c['folder_id']}' in parents and trashed = false and name = '{name}'"
    page=None
    files=[]
    while True:
        result=service.files().list(q=q,fields="nextPageToken,incompleteSearch,files(id)",
            spaces="drive",pageSize=100,pageToken=page).execute()
        require(not result.get("incompleteSearch"),"WORKER_LIST_INCOMPLETE")
        files.extend(result["files"])
        page=result.get("nextPageToken")
        if not page:
            break
    require(len(files)<=1,"WORKER_DUPLICATE_NAME_HOLD")
    return files


def readback(service,c,item,file_id):
    f=service.files().get(fileId=file_id,fields=FIELDS,supportsAllDrives=True).execute()
    require(f["id"]==file_id and f["name"]==item["name"]
            and f["parents"]==[c["folder_id"]] and f["mimeType"]=="application/zip"
            and f["ownedByMe"] is True and f["shared"] is False
            and f["trashed"] is False and not f.get("driveId")
            and int(f["size"])==len(item["raw"]),"WORKER_FILE_SCOPE")
    owner_only(service,file_id,c)
    raw=service.files().get_media(fileId=file_id,supportsAllDrives=True).execute()
    require(raw==item["raw"] and sha(raw)==item["sha256"]
            and (not f.get("sha256Checksum") or f["sha256Checksum"]==item["sha256"]),
            "WORKER_READBACK_MISMATCH")
    # Recheck metadata after download to detect ordinary concurrent changes.
    end=service.files().get(fileId=file_id,fields=FIELDS,supportsAllDrives=True).execute()
    require(f==end,"WORKER_CONCURRENT_CHANGE")
    owner_only(service,file_id,c)
    return dict(role=item["role"],name=item["name"],drive_file_id=file_id,
                size=len(raw),sha256=sha(raw),created_utc=f["createdTime"],
                modified_utc=f["modifiedTime"])


def durable_new(path,obj):
    raw=(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
    path=Path(path)
    # Atomic no-replace publication; incomplete temp file is never a valid intent.
    fd,tmp=tempfile.mkstemp(prefix=".pending-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp,path)
        fd=os.open(path.parent,os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.unlink(tmp)


def create_only(service,c,item,state,media_factory):
    matches=list_matches(service,c,item["name"])
    path=state/(sha(item["name"].encode())+".intent.json")
    expected=dict(folder_id=c["folder_id"],account_permission_id=c["account_permission_id"],
                  name=item["name"],sha256=item["sha256"],size=len(item["raw"]))
    if path.exists():
        intent=parse(path.read_bytes())
        require({k:v for k,v in intent.items() if k!="id"}==expected,
                "WORKER_INTENT_MISMATCH")
        file_id=intent["id"]
        if matches:
            require(matches[0]["id"]==file_id,"WORKER_INTENT_NAME_CONFLICT")
            return dict(readback(service,c,item,file_id),action="REUSED")
    elif matches:
        return dict(readback(service,c,item,matches[0]["id"]),action="REUSED")
    else:
        ids=service.files().generateIds(count=1,space="drive",type="files").execute()["ids"]
        require(len(ids)==1 and re.fullmatch("[A-Za-z0-9_-]+",ids[0]),
                "WORKER_GENERATED_ID")
        file_id=ids[0]
        durable_new(path,dict(expected,id=file_id))
    # Retry only with this same durable preallocated ID, never allocate a new
    # one after an indeterminate create. Caller reruns after a failed response.
    try:
        service.files().create(body=dict(id=file_id,name=item["name"],
            parents=[c["folder_id"]],mimeType="application/zip"),
            media_body=media_factory(item["raw"]),fields="id",
            supportsAllDrives=True).execute(num_retries=0)
    except Exception as exc:
        # 409 may mean the previous create succeeded even if listing was stale.
        if getattr(getattr(exc,"resp",None),"status",None)!=409:
            raise RuntimeError("WORKER_CREATE_UNCERTAIN_REUSE_INTENT") from None
    return dict(readback(service,c,item,file_id),action="CREATE_OR_RESUME")


def process(service,c,items,state,write,media_factory):
    identity(service,c)
    rows=[]
    # Check all existing matches before creating anything.
    for item in items:
        hits=list_matches(service,c,item["name"])
        if hits:
            readback(service,c,item,hits[0]["id"])
    for item in items:
        if write:
            rows.append(create_only(service,c,item,state,media_factory))
        else:
            hits=list_matches(service,c,item["name"])
            rows.append(dict(readback(service,c,item,hits[0]["id"]),action="WOULD_REUSE")
                        if hits else dict(role=item["role"],name=item["name"],
                        sha256=item["sha256"],action="WOULD_CREATE"))
    identity(service,c)
    return dict(version="kalman-challenger-private-archive-worker-v1",
                status="PRIVATE_ARCHIVE_READBACK_NOT_FORWARD" if write else "PLAN_ONLY_NOT_FORWARD",
                research_only=True,approved_live=False,source_finality_certified=False,
                forward_signals_created=0,files=rows,drive_account="Taehoon",
                drive_folder_id=c["folder_id"],immutable_retention_certified=False)


def private_file(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_mode&0o077==0,
            "WORKER_PRIVATE_FILE_PERMISSIONS")
    return p


def connect(c):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    p=private_file(os.environ["CHALLENGER_DRIVE_OAUTH_FILE"])
    info=parse(p.read_bytes())
    require(info.get("type")=="authorized_user"
            and set(info.get("scopes",[]))=={SCOPE}
            and info.get("token_uri","https://oauth2.googleapis.com/token")==
                "https://oauth2.googleapis.com/token","WORKER_OAUTH_SCOPE")
    creds=Credentials.from_authorized_user_info(info,scopes=[SCOPE])
    service=build("drive","v3",credentials=creds,cache_discovery=False)
    return service,lambda raw:MediaIoBaseUpload(io.BytesIO(raw),mimetype="application/zip",
                                               resumable=False)


def self_test():
    # Fake API exercises create/reuse/conflict and uncertain-response recovery.
    from types import SimpleNamespace
    class Call:
        def __init__(self,f): self.f=f
        def execute(self,**kw): return self.f()
    class Fake:
        def __init__(self):
            self.rows={}
            self.creates=0
            self.generated=0
            self.uncertain=False
            self.wrong=False
            self.shared=False
        def about(self):
            return SimpleNamespace(get=lambda **kw:Call(lambda:{"user":{
                "permissionId":"wrong" if self.wrong else "owner","emailAddress":"test@example.invalid"}}))
        def permissions(self):
            return SimpleNamespace(list=lambda **kw:Call(lambda:{"permissions":[
                {"id":"owner","type":"user","role":"owner"}]+(
                [{"id":"other","type":"anyone","role":"reader"}] if self.shared else [])}))
        def files(self): return self
        def get(self,fileId,**kw):
            def get():
                if fileId=="folder":
                    return dict(id="folder",name=FOLDER_NAME,parents=["parent"],
                        mimeType="application/vnd.google-apps.folder",ownedByMe=True,
                        shared=False,trashed=False,capabilities={"canAddChildren":True})
                return dict(self.rows[fileId][0])
            return Call(get)
        def list(self,q,**kw):
            name=q.rsplit("name = '",1)[1][:-1]
            return Call(lambda:{"files":[{"id":k} for k,v in self.rows.items()
                                         if v[0]["name"]==name]})
        def generateIds(self,**kw):
            self.generated+=1
            return Call(lambda:{"ids":["id"+str(self.generated)]})
        def create(self,body,media_body,**kw):
            def create():
                self.creates+=1
                i=body["id"]
                require(i not in self.rows,"FAKE_DUPLICATE_CREATE")
                self.rows[i]=(dict(body,ownedByMe=True,shared=False,trashed=False,
                    size=str(len(media_body)),sha256Checksum=sha(media_body),
                    createdTime="2026-11-24T00:00:00Z",modifiedTime="2026-11-24T00:00:00Z"),media_body)
                if self.uncertain:
                    self.uncertain=False
                    raise TimeoutError()
                return {"id":i}
            return Call(create)
        def get_media(self,fileId,**kw): return Call(lambda:self.rows[fileId][1])
    c=dict(account_permission_id="owner",account_email="test@example.invalid",
           folder_id="folder",parent_id="parent")
    items=[dict(role="synthetic",name="test.zip",raw=b"fixture",sha256=sha(b"fixture"))]
    f=Fake()
    with tempfile.TemporaryDirectory() as t:
        state=Path(t)
        r=process(f,c,items,state,False,lambda x:x)
        require(r["files"][0]["action"]=="WOULD_CREATE" and f.creates==0,"TEST_PLAN")
        f.uncertain=True
        try:
            process(f,c,items,state,True,lambda x:x)
        except RuntimeError as exc:
            require(str(exc)=="WORKER_CREATE_UNCERTAIN_REUSE_INTENT","TEST_UNCERTAIN")
        else:
            raise AssertionError("TEST_TIMEOUT_NOT_DETECTED")
        r=process(f,c,items,state,True,lambda x:x)
        require(r["files"][0]["action"]=="REUSED" and f.generated==f.creates==1,"TEST_IDEMPOTENT")
        f.rows["id2"]=f.rows["id1"]
        try:
            process(f,c,items,state,True,lambda x:x)
        except ValueError as exc:
            require(str(exc)=="ARCHIVE_WORKER_DUPLICATE_NAME_HOLD","TEST_DUPLICATE_VETO")
        else:
            raise AssertionError("TEST_DUPLICATE_NOT_BLOCKED")
        del f.rows["id2"]
        f.rows["id1"]=(f.rows["id1"][0],b"changed")
        for reason in ("WORKER_READBACK_MISMATCH","WORKER_WRONG_ACCOUNT","WORKER_PERMISSION_NOT_OWNER_ONLY"):
            f.wrong=reason=="WORKER_WRONG_ACCOUNT"
            f.shared=reason=="WORKER_PERMISSION_NOT_OWNER_ONLY"
            try:
                process(f,c,items,state,True,lambda x:x)
            except ValueError as exc:
                require(str(exc)=="ARCHIVE_"+reason,"TEST_VETO_REASON")
            else:
                raise AssertionError("TEST_VETO_MISSING")
        require(f.creates==1,"TEST_NO_OVERWRITE")
    print("CHALLENGER_PRIVATE_ARCHIVE_WORKER_SYNTHETIC_PASS")


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--self-test",action="store_true")
    a.add_argument("--mode",choices=("plan","archive"),default="plan")
    a.add_argument("--verify-inputs-only",action="store_true")
    for k in ("config","config-sha256","handoff","handoff-sha256","rehearsal",
              "rehearsal-sha256","commit","state-dir"):
        a.add_argument("--"+k)
    a.add_argument("--run",type=int)
    x=a.parse_args()
    if x.self_test:
        self_test()
        return
    require(all([x.handoff,x.handoff_sha256,x.rehearsal,x.rehearsal_sha256,x.commit,x.run]),
            "WORKER_INPUT_ARGUMENTS")
    items=inputs(x.handoff,x.handoff_sha256,x.rehearsal,x.rehearsal_sha256,x.run,x.commit)
    if x.verify_inputs_only:
        print(json.dumps(dict(status="ARCHIVE_INPUTS_VERIFIED_NO_DRIVE_NOT_FORWARD",
                              files=len(items),approved_live=False,forward_signals_created=0)))
        return
    require(not os.environ.get("GITHUB_ACTIONS"),"WORKER_PUBLIC_RUNNER_FORBIDDEN")
    require(all([x.config,x.config_sha256,x.state_dir]),"WORKER_PRIVATE_ARGUMENTS")
    c=parse(pinned(private_file(x.config),x.config_sha256))
    require(set(c)=={"account_label","account_email","account_permission_id","folder_id","parent_id"}
            and c["account_label"]=="Taehoon"
            and all(isinstance(v,str) and v.strip() for v in c.values()),"WORKER_PRIVATE_CONFIG")
    state=Path(x.state_dir)
    state.mkdir(mode=0o700,parents=True,exist_ok=True)
    require(not state.is_symlink() and state.stat().st_mode&0o077==0,"WORKER_PRIVATE_STATE")
    with (state/"worker.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        service,media=connect(c)
        result=process(service,c,items,state,x.mode=="archive",media)
        result.update(run_id=x.run,commit=x.commit,handoff_sha256=x.handoff_sha256,
                      rehearsal_sha256=x.rehearsal_sha256,protocol_sha256=PROTOCOL)
        if x.mode=="archive":
            # Append local receipts, never overwrite a prior audit.
            fd,tmp=tempfile.mkstemp(prefix=f"readback-GH{x.run}-",suffix=".json",dir=state)
            with os.fdopen(fd,"w") as f:
                json.dump(result,f,indent=2,allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
        print(json.dumps(dict(status=result["status"],files=len(result["files"]),
                              approved_live=False,forward_signals_created=0)))


if __name__=="__main__":
    main()
