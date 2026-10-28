#!/usr/bin/env python3
"""Read-only full QQ UID coverage across staging and legacy, with strict folder identity."""
import imaplib,json,os,urllib.parse
from collections import defaultdict
import incremental_sync as src

def main():
    session=src.authorize()
    def read(tab,range_):
        u=src.endpoint("/values/"+urllib.parse.quote("'"+tab+"'!"+range_,safe=""))
        return src.api(session,"GET",u).get("values",[])
    stage=read("CSS Git Ingest","A1:R100000")
    old=read("All Emails","A1:N100000")
    if not stage or stage[0]!=src.COLS or not old or old[0][0].lower()!="uid":
        raise RuntimeError("SOURCE_SCHEMA_MISMATCH")
    staged={r[0] for r in stage[1:] if r}
    legacy=defaultdict(set)
    for r in old[1:]:
        if not r or not r[0]:continue
        value=str(r[0]).strip()
        upper=value.upper()
        if upper.startswith("SENT:"):
            folder="SENT"; number=value[5:]
        elif upper.startswith("INBOX:"):
            folder="INBOX";number=value[6:]
        elif value.isdigit():
            folder="INBOX";number=value
        else:continue
        if number.isdigit():legacy[folder].add(str(int(number)))
    result=[]
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
        im.login(os.environ["CSS_QQ_MAIL_ADDRESS"],os.environ["CSS_QQ_MAIL_AUTH_CODE"])
        folders=src.folder_names(im)
        sent=next((f for f,t in folders if "\\sent" in t or f.lower() in ("sent messages","sent","sent items")),None)
        if not sent:raise RuntimeError("SENT_FOLDER_MISSING")
        for name,folder in [("INBOX","INBOX"),("SENT",sent)]:
            status,_=im.select('"'+folder.replace('"','')+'"',readonly=True)
            if status!="OK":raise RuntimeError("SELECT_FAILED")
            _,uv=im.response("UIDVALIDITY")
            validity=uv[0].decode("ascii","replace")
            status,matches=im.uid("SEARCH",None,"ALL")
            if status!="OK":raise RuntimeError("SEARCH_ALL_FAILED")
            uids={x.decode("ascii") for x in (matches[0] or b"").split()}
            in_stage={uid for uid in uids if folder+"|"+validity+"|"+uid in staged}
            in_legacy=uids & legacy[name]
            union=in_stage | in_legacy
            result.append({"folder":name,"imap_total":len(uids),"staging":len(in_stage),
                "legacy_uid_match_unverified":len(in_legacy),"covered_by_either_uid":len(union),
                "unmatched_uid":len(uids-union),"legacy_uid_identity_caveat":"Legacy UIDVALIDITY missing; UID match is provisional"})
        im.logout()
    print("QQ_LEGACY_FULL_COVERAGE "+json.dumps({"folders":result,
        "all_current_uids_provisionally_covered":all(x["unmatched_uid"]==0 for x in result),
        "warning":"Legacy UIDVALIDITY is absent; cannot certify historical identity by UID alone."},sort_keys=True))
if __name__=="__main__":main()
