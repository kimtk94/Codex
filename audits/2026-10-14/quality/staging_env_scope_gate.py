"""Static fail-closed staging secret-scope gate, without secret values."""
import json
from pathlib import Path

SNAPSHOT=Path(__file__).resolve().parents[2]/"2026-10-18/staging_env_scope_snapshot.json"
RISK_KEYS={"BLOB_READ_WRITE_TOKEN","INVESTMENT_HUB_INGEST_SECRET",
           "DATABASE_URL_READER","DATABASE_URL_WRITER","HUB_GATEWAY_SECRET",
           "TOSS_GATEWAY_URL","OPENAI_API_KEY"}

def assess(snapshot):
    def hold(reason, risky):
        return {"verdict":"STAGING_HOLD","reason":reason,
                "risky_names":sorted(set(risky)), "deployment_authorized":False}
    if snapshot.get("project_id")!="prj_MpQ3qSpSW4QBRvw6aPvS3BYUtFFt":
        return hold("WRONG_PROJECT",[])
    envs=snapshot.get("variables")
    if not isinstance(envs,list):
        return hold("ENV_INVENTORY_NOT_ATTESTED",[])
    names=[x.get("key") for x in envs if isinstance(x,dict)]
    if len(names)!=len(set(names)):
        return hold("DUPLICATE_OR_UNVERIFIED_ENV_NAMES",names)
    exposed=[x["key"] for x in envs if x.get("key") in RISK_KEYS
             and any(t in ("preview","production","development")
                     for t in x.get("target",[]))]
    if exposed:
        return hold("PRIVILEGED_VARS_PRESENT_IN_STAGING",exposed)
    if snapshot.get("sso_enabled") is not True and snapshot.get("password_protection") is not True:
        return hold("STAGING_ACCESS_PROTECTION_MISSING",[])
    if snapshot.get("blob_isolation_verified") is not True or snapshot.get("ingest_isolation_verified") is not True:
        return hold("CREDENTIAL_ISOLATION_NOT_ATTESTED",[])
    return {"verdict":"REQUIRES_SEPARATE_OPERATOR_APPROVAL",
            "deployment_authorized":False, "risky_names":[]}

if __name__=="__main__":
    print(json.dumps(assess(json.loads(SNAPSHOT.read_text())),sort_keys=True))
