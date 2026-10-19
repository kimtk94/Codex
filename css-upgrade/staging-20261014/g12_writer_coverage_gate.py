"""G12 release-targeted Sheet writer evidence inventory; no live services.

The 28 call sites below were derived from a SHA-pinned static audit of
production CSS. They are *candidate* write sites, not proven Sheet targets.
The default decision blocks promotion until separately reviewed evidence
is provided. No claimed runtime guard, Google Sheets CAS, or code patch.
"""
from __future__ import annotations

import collections
import hashlib
import json

SOURCE_SHA = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
# (source line, observed method, static risk class)
SITES = (
    (1673,"resize","STRUCTURAL"), (1871,"batch_clear","STRUCTURAL"),
    (1881,"update","UNKNOWN"), (1891,"set_with_dataframe","STRUCTURAL"),
    (2228,"update","UNKNOWN"), (2252,"update","UNKNOWN"),
    (2745,"update","UNKNOWN"), (2778,"update","UNKNOWN"),
    (2805,"append_rows","APPEND"), (2835,"resize","STRUCTURAL"),
    (2850,"update","UNKNOWN"), (6453,"resize","STRUCTURAL"),
    (7410,"batch_update","UNKNOWN"), (8806,"batch_update","UNKNOWN"),
    (10430,"batch_update","UNKNOWN"), (12246,"batch_update","UNKNOWN"),
    (12568,"batch_update","UNKNOWN"), (12648,"batch_update","UNKNOWN"),
    (15419,"batch_update","UNKNOWN"), (15517,"batch_update","UNKNOWN"),
    (15597,"batch_update","UNKNOWN"), (17134,"batch_update","UNKNOWN"),
    (17648,"set_with_dataframe","STRUCTURAL"),
    (19275,"sort","STRUCTURAL"),
    (20304,"batch_update","UNKNOWN"),
    (20876,"batch_update","UNKNOWN"),
    (20921,"clear","STRUCTURAL"),
    (22107,"batch_update","UNKNOWN"),
)
OBSERVED_RISKS = {
    "DESTRUCTIVE_OR_FULL_REWRITE_CANDIDATE":"STRUCTURAL",
    "API_EFFECT_UNKNOWN":"UNKNOWN",
    "STRUCTURAL_APPEND_CANDIDATE":"APPEND",
}

def baseline_digest():
    return hashlib.sha256(json.dumps(SITES,separators=(",",":")).encode()).hexdigest()

def analyze(inventory):
    if not isinstance(inventory,dict) or inventory.get("source_sha256") != SOURCE_SHA:
        return {"decision":"BLOCKED_SOURCE_FINGERPRINT","candidate_count":None,
                "confirmed_safe_sites":0,"release_authorized":False}
    sites=inventory.get("sites")
    if not isinstance(sites,list) or inventory.get("sites_truncated") is not False:
        return {"decision":"BLOCKED_INCOMPLETE_INVENTORY","candidate_count":None,
                "confirmed_safe_sites":0,"release_authorized":False}
    observed=[]
    for site in sites:
        if not isinstance(site,dict) or type(site.get("line")) is not int:
            return {"decision":"BLOCKED_MALFORMED_INVENTORY","candidate_count":None,
                    "confirmed_safe_sites":0,"release_authorized":False}
        risk=OBSERVED_RISKS.get(site.get("risk"))
        if risk is None or not isinstance(site.get("method"),str):
            return {"decision":"BLOCKED_MALFORMED_INVENTORY","candidate_count":None,
                    "confirmed_safe_sites":0,"release_authorized":False}
        observed.append((site["line"],site["method"],risk))
    if len(observed)!=len(set(observed)):
        decision="BLOCKED_DUPLICATE_CALL_SITES"
    elif tuple(observed)!=SITES or inventory.get("candidate_count")!=len(SITES):
        decision="BLOCKED_CALL_SITES_CHANGED"
    else:
        decision="BLOCKED_MISSING_WRITER_ISOLATION_EVIDENCE"
    by_class=dict(sorted(collections.Counter(x[2] for x in observed).items()))
    return {
        "decision":decision,
        "source_sha256":SOURCE_SHA,
        "baseline_sha256":baseline_digest(),
        "candidate_count":len(observed),
        "counts_by_risk":by_class,
        "confirmed_safe_sites":0,
        "all_sheet_targets_proven":False,
        "all_write_ranges_proven":False,
        "manual_edit_after_snapshot_proven":False,
        "full_g12_main_run_proven":False,
        "g16_all_sinks_isolated":False,
        "release_authorized":False,
    }

def fixture():
    risk_map={value:key for key,value in OBSERVED_RISKS.items()}
    return {
        "source_sha256":SOURCE_SHA,
        "candidate_count":len(SITES),
        "sites_truncated":False,
        "sites":[{"line":l,"method":m,"risk":risk_map[r]} for l,m,r in SITES],
    }

if __name__=="__main__":
    print(json.dumps(analyze(fixture()),sort_keys=True))
