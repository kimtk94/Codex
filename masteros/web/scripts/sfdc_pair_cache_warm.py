"""Explicit read-only Salesforce prefetch for the local Oppo/Quote web.

Warms a short-TTL, user-private SQLite cache with the selected Salesforce list
and up to five exact-parent Quote bundles. No Windows scheduled tasks, write
operations, customer dumps, GitHub secrets, or cloud synchronization.
"""
import json
import sys
import time
from sfdc_pair_cache import key_for, lookup, save, live_meta, stats

MAX_INPUT_BYTES=1200
MAX_BUNDLES=5


def validate(request):
    if not isinstance(request,dict) or request.get("mode")!="WARM":
        raise ValueError("CACHE_WARM_MODE_INVALID")
    limit=request.get("limit",3)
    offset=request.get("offset",0)
    if (not isinstance(limit,int) or isinstance(limit,bool) or limit<1 or limit>MAX_BUNDLES
            or not isinstance(offset,int) or isinstance(offset,bool) or offset<0 or offset>29):
        raise ValueError("CACHE_WARM_BATCH_INVALID")
    return limit,offset


def warm(request):
    limit,offset=validate(request)
    from playwright.sync_api import sync_playwright
    from sfdc_record_catalog import list_items,linked_oppo_quote_bundle
    started=time.monotonic()
    list_request={"resource":"opportunity","mode":"list","query":""}
    saved_list=0
    sampled=0
    cached_bundle=0
    verified_single=0
    price_holds=0
    unmatched=0
    source_failures=0
    available=lookup(list_request)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.connect_over_cdp("http://127.0.0.1:9222",timeout=12000)
            page=browser.contexts[0].new_page()
            try:
                # Refresh the visible selection from Salesforce to avoid
                # silently preloading an outdated list.
                listing=list_items(page,"opportunity","")
                if listing.get("status")!="PASS":
                    return {"status":"SOURCE_UNAVAILABLE","stage":"OPPORTUNITY_LIST",
                        "cache":stats(),"crm_writes":0}
                saved_list=int(save(list_request,listing))
                records=listing.get("records") or []
                for row in records[offset:offset+limit]:
                    rid=row.get("id")
                    source={"resource":"opportunity","mode":"bundle","recordId":rid}
                    if key_for(source) is None:
                        source_failures+=1
                        continue
                    if lookup(source) is not None:
                        cached_bundle+=1
                        continue
                    sampled+=1
                    try:
                        result=linked_oppo_quote_bundle(page,rid)
                        if result.get("selectionStatus")=="EXACT_ONE":
                            if save(source,result):
                                cached_bundle+=1
                                q=result["linkedQuotes"][0]
                                if q.get("pricingStatus")=="VERIFIED_PROCESS_LINES" and q.get("sourceVatRateVerified10Pct") is True:
                                    verified_single+=1
                                else:
                                    price_holds+=1
                            else:
                                source_failures+=1
                        else:
                            unmatched+=1
                    except Exception:
                        source_failures+=1
            finally:
                page.close()
    except Exception:
        return {"status":"SOURCE_UNAVAILABLE","stage":"SFDC_SESSION",
            "list_synced":saved_list,"sampled":sampled,
            "cache":stats(),"crm_writes":0}
    state="PASS" if saved_list and source_failures==0 else "PARTIAL" if saved_list else "SOURCE_UNAVAILABLE"
    return {"status":state,"list_synced":saved_list,
        "sampled":sampled,"bundles_available":cached_bundle,
        "source_price_verified":verified_single,"source_price_hold":price_holds,
        "no_unique_quote":unmatched,"source_failures":source_failures,
        "batch_offset":offset,"batch_limit":limit,
        "elapsed_seconds":round(time.monotonic()-started,1),
        "cache":stats(),"crm_writes":0,"read_only":True}


def main():
    try:
        data=sys.stdin.buffer.read(MAX_INPUT_BYTES+1)
        if len(data)>MAX_INPUT_BYTES or not data:
            raise ValueError("WARM_INPUT_TOO_LARGE")
        result=warm(json.loads(data.decode("utf-8")))
    except (TypeError,ValueError,UnicodeError) as exc:
        result={"status":"BLOCK","code":str(exc) if str(exc).isupper() else "WARM_INPUT_INVALID","crm_writes":0}
    except Exception:
        result={"status":"SOURCE_UNAVAILABLE","code":"SFDC_CACHE_WARM_FAILED","crm_writes":0}
    print(json.dumps(result,ensure_ascii=False,separators=(",",":")))


if __name__=="__main__":
    main()
