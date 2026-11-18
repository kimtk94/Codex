"""Local-only native Salesforce Save gate: immutable queue + verified per-record evidence.

This is the *write path* gate. GitHub Actions only executes synthetic tests;
customer/price evidence and any actual browser session remain on the laptop.
A Salesforce click is forbidden unless all guards pass on EVERY request.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import secrets
import time
from contextlib import contextmanager

from oppo_quote_save_preflight import audit_save_preflight

REQUEST_ID = re.compile(r"^OPPOQUOTE-[a-f0-9]{24}$")
TOKEN = re.compile(r"^[a-f0-9]{48}$")
DIGEST = re.compile(r"^SFDC-REVIEW-[a-f0-9]{24}$")
STAGE = {"OPPORTUNITY", "QUOTATION"}
MAX_FILE_SIZE = 75000
SESSION_SECONDS = 180

def sha_canonical(canonical):
    # Matches the already deployed JS queue ID calculation (insertion order).
    body = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    # JSON.stringify does not escape non-ASCII; JS quote canonical key ordering is retained.
    return "OPPOQUOTE-" + sha256(body.encode("utf-8")).hexdigest()[:24]

def private_base(home: str | None = None):
    root = home or os.environ.get("LOCALAPPDATA")
    if not root:
        raise ValueError("NO_PRIVATE_LAPTOP_FOLDER")
    return Path(root)

def _read(path: Path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("PRIVATE_FILE_INVALID")
    return json.loads(path.read_text(encoding="utf-8-sig"))

def paths(request_id: str, home: str | None = None):
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError("INVALID_REQUEST_ID")
    home_path = private_base(home)
    return {
        "queue":home_path / "SFDC_Oppo_Quote_Approval_Requests" / (request_id + ".json"),
        "root":home_path / "SFDC_Native_Save_Approvals" / request_id,
        "candidate":home_path / "SFDC_Native_Save_Approvals" / request_id / "candidate.json",
        "evidence":home_path / "SFDC_Native_Save_Approvals" / request_id / "evidence.json",
        "journal":home_path / "SFDC_Native_Save_Approvals" / request_id / "journal.json",
        "session":home_path / "SFDC_Native_Save_Approvals" / request_id / "session.json",
    }

def _gate(code: str, *, stage: str = "OPPORTUNITY", **extra):
    return {"status":"HOLD_NATIVE_SAVE", "code":code, "stage":stage,
        "allowed":False, "salesforce_write":False, "save_clicked":False,
        "crm_writes":0, **extra}

def check_candidate_binding(queue, candidate):
    """Reference same *exact* queued draft; no post-approval customer/price swap."""
    if not isinstance(queue, dict) or not isinstance(candidate, dict):
        return "INVALID_CANDIDATE"
    if queue.get("state") != "AWAITING_OPERATOR_APPROVAL":
        return "QUEUE_ALREADY_CONSUMED"
    if queue.get("approved") is not False or queue.get("requestedWrite") is not False:
        return "QUEUE_MUTATED"
    if queue.get("salesforceWrite") is not False or queue.get("savePermitted") is not False:
        return "QUEUE_UNTRUSTED"
    canonical = queue.get("canonical")
    if not isinstance(canonical, dict):
        return "QUEUE_CANONICAL_MISSING"
    p = canonical.get("proposed")
    if not isinstance(p, dict):
        return "QUEUE_PROPOSAL_MISSING"
    if candidate.get("operation") != "CREATE_NEW_OPPORTUNITY_AND_QUOTATION":
        return "NOT_PAIRED_CREATE"
    checks = (
        ("opportunity_name", p.get("name")),
        ("quotation_name", p.get("name")),
        ("close_date_kst", p.get("closeDate")),
        ("description", p.get("description")),
    )
    for key, expected in checks:
        if candidate.get(key) != expected or not expected:
            return "REQUEST_BINDING_" + key.upper()
    if p.get("accountMode") != "KEEP" and p.get("accountMode") != "CHANGE":
        return "UNVERIFIED_CUSTOMER_MODE"
    for key, source in (("account_id",p.get("account",{}).get("id")),
                        ("contact_id",p.get("contact",{}).get("id"))):
        if not source or candidate.get(key) != source:
            return "REQUEST_BINDING_" + key.upper()
    old_products = p.get("products")
    new_products = candidate.get("products")
    if not isinstance(old_products,list) or not isinstance(new_products,list):
        return "PRODUCTS_NOT_VERIFIED"
    if len(old_products) != len(new_products) or not 1 <= len(old_products) <= 8:
        return "PRODUCTS_NOT_EQUAL"
    for old, new in zip(old_products,new_products):
        if not isinstance(old,dict) or not isinstance(new,dict):
            return "PRODUCT_SHAPE_INVALID"
        # Source Quote Product ID, distinct from the SFDC Product master ID.
        if new.get("source_reference_product_id") != old.get("id"):
            return "PRODUCT_SOURCE_REFERENCE_CHANGED"
        expected_process_ids = old.get("processIds")
        lines = new.get("processes")
        if (not isinstance(expected_process_ids,list) or
            not isinstance(lines,list) or
            [x.get("process_id") for x in lines if isinstance(x,dict)] != expected_process_ids):
            return "PROCESS_REFERENCE_SET_CHANGED"
        if not all(isinstance(x,dict) for x in lines):
            return "PROCESS_LINES_INVALID"
    # Separate Quotation Fee kept explicit; never clone "KEEP" fees implicitly.
    if (p.get("quoteFeeMode") != "EXCLUDE" or
        candidate.get("quote_fee",{}).get("mode") != "EXCLUDE"):
        return "FEE_REQUIRES_SEPARATE_NATIVE_VERIFICATION"
    if candidate.get("expected_net_krw") in (None,"") or (
        candidate.get("expected_net_krw") != candidate.get("opportunity_amount_krw")
    ):
        return "NATIVE_QUOTE_OPPO_AMOUNT_MISMATCH"
    return None

def load_verified_request(request_id, home=None, *, asof_utc=None):
    try:
        found = paths(request_id,home)
        queue = _read(found["queue"])
        if queue.get("requestId") != request_id or (
            sha_canonical(queue.get("canonical")) != request_id
        ):
            return _gate("QUEUE_DIGEST_MISMATCH"), None
        candidate = _read(found["candidate"])
        evidence = _read(found["evidence"])
        mismatch = check_candidate_binding(queue,candidate)
        if mismatch:
            return _gate(mismatch), None
        duplicates = evidence.get("duplicate_check")
        if isinstance(duplicates,dict) and duplicates.get("scope") == "SOURCE_RECORD_ID_SNAPSHOT":
            ref=queue["canonical"]["reference"]
            if (candidate.get("source_opportunity_id") != ref.get("opportunityId") or
                candidate.get("source_quotation_id") != ref.get("sourceQuoteId")):
                return _gate("SOURCE_REFERENCE_NATIVE_ID_BINDING_MISMATCH"), None
        result = audit_save_preflight(candidate,evidence,asof_utc=asof_utc)
        if not result.get("ready_for_review") or not DIGEST.fullmatch(
            str(result.get("approval_digest",""))
        ):
            return _gate("SAVE_PREFLIGHT_HOLD",
                reasons=result.get("reason_codes",[])[:25]), None
        return {"status":"VALIDATED_RECORD",
            "approval_digest":result["approval_digest"],
            "net_krw":result["expected_net_krw"],
            "vat_krw":result["expected_vat_krw"],
            "gross_krw":result["expected_gross_krw"],
            "name":candidate["opportunity_name"],
            "original_opportunity_id":queue["canonical"]["reference"].get("opportunityId",""),
            "original_quotation_id":queue["canonical"]["reference"].get("sourceQuoteId",""),
            "existing_opportunity_ids":(
                duplicates.get("matching_opportunity_ids",[])
                if isinstance(duplicates,dict) and duplicates.get("scope")=="SOURCE_RECORD_ID_SNAPSHOT"
                else []
            ),
            "existing_quotation_ids":(
                duplicates.get("matching_quotation_ids",[])
                if isinstance(duplicates,dict) and duplicates.get("scope")=="SOURCE_RECORD_ID_SNAPSHOT"
                else []
            ),
            "identity_method":"NATIVE_SFDC_ID_NOT_NAME",
            "account_id":candidate["account_id"],
            "contact_id":candidate["contact_id"],
            "account_name":queue["canonical"]["proposed"].get("account",{}).get("name") or "",
            "contact_name":queue["canonical"]["proposed"].get("contact",{}).get("name") or "",
            "progress_description":candidate["description"],
            "service_line":candidate["service_line"],
            "forecast_category":candidate["forecast_category"],
            "quote_name":candidate["quotation_name"],
            "quote_product_count":len(candidate["products"]),
            "native_product_process_rows":result["verified_process_row_count"],
            "stage":candidate["stage"],
            "currency":candidate["currency"],
            "close_date_kst":candidate["close_date_kst"],
            "request_id":request_id}, found
    except (OSError,KeyError,ValueError,TypeError,AttributeError,OverflowError,UnicodeError):
        return _gate("PRIVATE_APPROVED_SOURCE_UNAVAILABLE"), None

def _atomic_write(path:Path, contents:dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+"."+secrets.token_hex(6)+".tmp")
    with temporary.open("x",encoding="utf8") as stream:
        json.dump(contents,stream,ensure_ascii=False,indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary,path)

def read_journal(files):
    journal=files["journal"]
    if not journal.exists():
        return {"state":"NOT_STARTED","opportunity_id":None,"quotation_id":None}
    try:
        obj=_read(journal)
        if obj.get("state") not in (
            "NOT_STARTED","OPPORTUNITY_CLICK_STARTED","OPPORTUNITY_SAVED",
            "QUOTATION_CLICK_STARTED","QUOTATION_SAVED",
            "UNKNOWN_AFTER_CLICK","HOLD_RECONCILE"
        ):
            raise ValueError("UNKNOWN_JOURNAL")
        return obj
    except Exception:
        return {"state":"HOLD_RECONCILE","error":"INVALID_JOURNAL"}

def create_session(files,review,stage,snapshot, now=None):
    """One-use approval token after live precheck, expires in 180 seconds."""
    now = time.time() if now is None else now
    key=secrets.token_hex(24)
    data={"stage":stage,"approval_digest":review["approval_digest"],
        "request_id":review["request_id"],"token_hash":sha256(key.encode()).hexdigest(),
        "snapshot":snapshot,"created_unix":now,"used":False}
    _atomic_write(files["session"],data)
    return key

def consume_session(files,review,stage,token,digest,*,snapshot=None,now=None):
    now=time.time() if now is None else now
    if not isinstance(token,str) or not TOKEN.fullmatch(token):
        return "INVALID_SAVE_SESSION_TOKEN"
    try:
        obj=_read(files["session"])
    except Exception:
        return "SAVE_SESSION_ABSENT"
    if obj.get("used") is True or obj.get("stage")!=stage or (
        obj.get("request_id")!=review["request_id"] or
        obj.get("approval_digest")!=digest or digest!=review["approval_digest"]):
        return "SAVE_SESSION_REPLAY_OR_MISMATCH"
    created=obj.get("created_unix")
    if not isinstance(created,(float,int)) or not 0 <= now-created <= SESSION_SECONDS:
        return "SAVE_SESSION_EXPIRED"
    if obj.get("token_hash")!=sha256(token.encode()).hexdigest():
        return "SAVE_SESSION_TOKEN_MISMATCH"
    if not isinstance(snapshot,str) or obj.get("snapshot")!=snapshot:
        return "NATIVE_FORM_CHANGED_SINCE_PRECHECK"
    _atomic_write(files["session"],{**obj,"used":True})
    return None

@contextmanager
def exclusive_transaction(files):
    """Prevent double-click/two-tab concurrent native Save attempts."""
    file=files["root"]/"writer.lock"
    file.parent.mkdir(parents=True,exist_ok=True)
    fd=None
    try:
        fd=os.open(str(file),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        os.write(fd,str(os.getpid()).encode())
        os.close(fd);fd=None
        yield
    finally:
        if fd is not None:os.close(fd)
        # Never auto-remove a stale lock after crash; the operator must reconcile.
        # On a clean run the caller releases this lock explicitly.

def release_lock(files):
    (files["root"]/"writer.lock").unlink(missing_ok=True)

def before_click(files,stage,review,*,opportunity_id=None):
    journal=read_journal(files)
    state=journal["state"]
    if stage=="OPPORTUNITY":
        if state!="NOT_STARTED":
            return "OPPORTUNITY_ALREADY_ATTEMPTED_OR_SAVED"
        newstate="OPPORTUNITY_CLICK_STARTED"
        rec={"opportunity_id":None,"quotation_id":None}
    elif stage=="QUOTATION":
        if state!="OPPORTUNITY_SAVED" or journal.get("opportunity_id")!=opportunity_id:
            return "QUOTATION_PARENT_NOT_VERIFIED"
        newstate="QUOTATION_CLICK_STARTED"
        rec={"opportunity_id":opportunity_id,"quotation_id":None}
    else:return "INVALID_STAGE"
    _atomic_write(files["journal"],{"state":newstate,
        "request_id":review["request_id"],
        "approval_digest":review["approval_digest"],
        "updated_at_utc":datetime.now(timezone.utc).isoformat(),**rec})
    return None

def created_id_is_distinct(stage,record_id,review):
    """A same-name Save only succeeds if the *new* native Salesforce ID is new.

    The source Quote/Oppo may carry exactly the same Name. A URL that points
    to an existing 006/a0P is NOT evidence of a newly created record.
    """
    if not isinstance(review,dict) or stage not in STAGE:
        return False
    prefix="006" if stage=="OPPORTUNITY" else "a0P"
    if not isinstance(record_id,str) or not record_id.startswith(prefix) or not SFID.fullmatch(record_id):
        return False
    original_key=("original_opportunity_id" if stage=="OPPORTUNITY" else "original_quotation_id")
    existing_key=("existing_opportunity_ids" if stage=="OPPORTUNITY" else "existing_quotation_ids")
    existing=review.get(existing_key,[])
    if not isinstance(existing,list) or not all(isinstance(x,str) for x in existing):
        return False
    if record_id==review.get(original_key) or record_id in existing:
        return False
    return True


def after_click(files,stage,record_id):
    journal=read_journal(files)
    if stage=="OPPORTUNITY" and journal["state"]=="OPPORTUNITY_CLICK_STARTED" and (
        re.fullmatch(r"006[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",record_id or "")
    ):
        journal["opportunity_id"]=record_id
        journal["state"]="OPPORTUNITY_SAVED"
    elif stage=="QUOTATION" and journal["state"]=="QUOTATION_CLICK_STARTED" and (
        re.fullmatch(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",record_id or "")
    ):
        journal["quotation_id"]=record_id
        journal["state"]="QUOTATION_SAVED"
    else:
        journal["state"]="UNKNOWN_AFTER_CLICK"
        _atomic_write(files["journal"],journal)
        return False
    journal["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    _atomic_write(files["journal"],journal)
    return True

def mark_unknown(files):
    journal=read_journal(files)
    journal["state"]="UNKNOWN_AFTER_CLICK"
    journal["updated_at_utc"]=datetime.now(timezone.utc).isoformat()
    _atomic_write(files["journal"],journal)
