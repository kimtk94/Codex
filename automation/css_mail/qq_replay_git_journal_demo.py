#!/usr/bin/env python3
"""Synthetic Git-ref CAS rehearsal for a FUTURE private QQ invoice journal.

The main Codex repository is PUBLIC and must never store actual invoice keys,
HMAC digests, financial receipts or account data. This module only initializes
a disposable local bare Git directory with fabricated invoices. It does not
call GitHub, Google Sheets, mail or any network service.

A Git ref compare-and-swap is atomic within ONE Git repository. It is NOT
atomic with Google Sheets and cannot exclude external Sheets writers. A
simulated success is NOT an authenticated human approval or live receipt.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
from pathlib import Path
import re
import subprocess
import tempfile

STATES=("PREPARED","WRITE_UNKNOWN","VERIFIED","ABORTED")
ZERO_SHA="0"*40
REF_PREFIX="refs/qq-replay-synthetic/"
KEYS=("invoice_number","amount_krw","imap_folder","imap_uid",
      "uidvalidity","issued_month")
DEMO_KEY=b"synthetic-only-local-git-cas-test-key-do-not-use-for-real"


def _check_case(case):
    if not isinstance(case,dict) or set(case)!=set(KEYS):
        raise ValueError("JOURNAL_CASE_SCHEMA_INVALID")
    normalized={k:str(case[k]) for k in KEYS}
    if (not re.fullmatch(r"[0-9]{10,15}",normalized["invoice_number"])
            or not re.fullmatch(r"[0-9]+",normalized["amount_krw"])
            or int(normalized["amount_krw"])<=0
            or normalized["imap_folder"]!="INBOX"
            or not re.fullmatch(r"[0-9]+",normalized["imap_uid"])
            or not re.fullmatch(r"[0-9]+",normalized["uidvalidity"])
            or normalized["issued_month"]!=""):
        raise ValueError("JOURNAL_CASE_VALUES_INVALID")
    return normalized


def opaque_identity(secret,case):
    """Per-case stable key and bound payload proof, used ONLY in local tests."""
    if not isinstance(secret,bytes) or len(secret)<32 or secret==DEMO_KEY:
        raise ValueError("JOURNAL_PRODUCTION_HMAC_KEY_NOT_CONFIGURED")
    normalized=_check_case(case)
    identity=(normalized["invoice_number"]+"|"+normalized["imap_folder"]+
              "|"+normalized["imap_uid"]+"|"+normalized["uidvalidity"])
    digest=hmac.new(secret, identity.encode("ascii"),hashlib.sha256).hexdigest()
    payload=json.dumps(normalized,sort_keys=True,separators=(",",":"))
    payload_digest=hmac.new(secret,payload.encode("utf-8"),
                            hashlib.sha256).hexdigest()
    return digest,payload_digest


def validate_transition(before,after):
    """Allowlisted *synthetic* state machine; never grants a live write."""
    if not isinstance(after,dict):
        return "RECEIPT_INVALID_HOLD"
    expected={"schema_version","case_key","payload_digest","attempt_nonce",
              "revision","state"}
    if set(after)!=expected or after.get("schema_version")!=1:
        return "RECEIPT_INVALID_HOLD"
    if (not isinstance(after.get("case_key"),str) or
        not re.fullmatch("[a-f0-9]{64}",after["case_key"]) or
        not isinstance(after.get("payload_digest"),str) or
        not re.fullmatch("[a-f0-9]{64}",after["payload_digest"]) or
        not isinstance(after.get("attempt_nonce"),str) or
        not re.fullmatch("[A-Za-z0-9_-]{16,64}",after["attempt_nonce"]) or
        type(after.get("revision")) is not int or after["revision"]<1 or
        after.get("state") not in STATES):
        return "RECEIPT_INVALID_HOLD"
    if before is None:
        return "SIMULATED_TRANSITION_OK" if (
            after["revision"]==1 and after["state"]=="PREPARED"
        ) else "RECEIPT_INVALID_TRANSITION_HOLD"
    if not isinstance(before,dict) or set(before)!=expected:
        return "RECEIPT_PREVIOUS_INVALID_HOLD"
    if any(after[k]!=before[k] for k in
           ("schema_version","case_key","payload_digest","attempt_nonce")):
        return "RECEIPT_BINDING_CHANGED_HOLD"
    if after["revision"]!=before["revision"]+1:
        return "RECEIPT_SEQUENCE_MISMATCH_HOLD"
    nexts={
        "PREPARED":{"WRITE_UNKNOWN","ABORTED"},
        "WRITE_UNKNOWN":{"VERIFIED"},
        "VERIFIED":set(),
        "ABORTED":set(),
    }
    if after["state"] not in nexts.get(before.get("state"),set()):
        return "RECEIPT_INVALID_TRANSITION_HOLD"
    return "SIMULATED_TRANSITION_OK"


def _git(root,args,input_text=None):
    """Local-only Git plumbing; must point to a disposable bare Git repo."""
    if not (Path(root)/"HEAD").is_file() or not (Path(root)/"objects").is_dir():
        raise ValueError("JOURNAL_LOCAL_BARE_REPO_REQUIRED")
    return subprocess.run(["git","--git-dir",str(root),*args],
                          input=input_text,text=True,capture_output=True,
                          timeout=12,check=False)


def _store_blob(root,event):
    doc=json.dumps(event,sort_keys=True,separators=(",",":"))
    r=_git(root,["hash-object","-w","--stdin"],input_text=doc)
    if r.returncode!=0 or not re.fullmatch(r"[a-f0-9]{40}",r.stdout.strip()):
        raise RuntimeError("JOURNAL_LOCAL_BLOB_STORE_FAILED")
    return r.stdout.strip()


def _cas(root,ref,after,expected_old):
    if not ref.startswith(REF_PREFIX) or not re.fullmatch(
            "[a-f0-9]{64}",ref[len(REF_PREFIX):]):
        raise ValueError("JOURNAL_LOCAL_REF_NOT_SYNTHETIC")
    if not re.fullmatch(r"[a-f0-9]{40}",expected_old):
        raise ValueError("JOURNAL_CAS_OLD_SHA_INVALID")
    sha=_store_blob(root,after)
    r=_git(root,["update-ref",ref,sha,expected_old])
    return r.returncode==0


def _read(root,ref):
    r=_git(root,["rev-parse","--verify",ref])
    if r.returncode!=0:
        return None,None
    sha=r.stdout.strip()
    content=_git(root,["cat-file","-p",sha])
    if content.returncode!=0:
        return "CORRUPT",sha
    try:
        value=json.loads(content.stdout)
    except ValueError:
        value="CORRUPT"
    return value,sha


def _sim_case():
    return {"invoice_number":"209126999001","amount_krw":"12345",
            "imap_folder":"INBOX","imap_uid":"125",
            "uidvalidity":"1098","issued_month":""}


def demo():
    """Demonstrate Git CAS and unknown-result hold; output counts only."""
    # A synthetic test key is not a production secret. Keep it only in the
    # ephemeral runner; NEVER log even synthetic HMAC values.
    synthetic_secret=b"another-fabricated-local-only-secret-key-1234567890"
    case=_sim_case()
    key,digest=opaque_identity(synthetic_secret,case)
    ref=REF_PREFIX+key
    prepared={"schema_version":1,"case_key":key,"payload_digest":digest,
              "attempt_nonce":"synthetic_nonce_1234","revision":1,
              "state":"PREPARED"}
    unknown={**prepared,"revision":2,"state":"WRITE_UNKNOWN"}
    with tempfile.TemporaryDirectory(prefix="qq-replay-synthetic-") as d:
        root=Path(d)/"journal.git"
        init=subprocess.run(["git","init","--bare","--quiet",str(root)],
                            text=True,capture_output=True,timeout=12)
        if init.returncode:
            raise RuntimeError("JOURNAL_DEMO_GIT_UNAVAILABLE")
        first=_cas(root,ref,prepared,ZERO_SHA)
        duplicate=_cas(root,ref,prepared,ZERO_SHA)
        state,old=_read(root,ref)
        missing_reply_hold=state is not None and duplicate is False
        result={
            "status":"SIMULATED_LOCAL_ONLY",
            "synthetic_case_count":1,
            "synthetic_claim_succeeded":int(first),
            "duplicate_create_ref_blocked":int(not duplicate),
            "uncertain_reply_would_hold":int(missing_reply_hold),
            "live_github_refs_written":0,
            "live_sheets_writes":0,
            "live_cursor_writes":0,
            "real_approved_cases":0,
            "authenticated_receipts_verified":0,
            "cross_system_atomicity_verified":0,
            "production_status":"HOLD",
        }
        if validate_transition(prepared,unknown)!="SIMULATED_TRANSITION_OK":
            raise RuntimeError("JOURNAL_DEMO_STATE_MACHINE_INVALID")
        return result


if __name__=="__main__":
    print("QQ_REPLAY_GIT_JOURNAL_DEMO="+json.dumps(demo(),sort_keys=True))
