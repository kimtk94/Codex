#!/usr/bin/env python3
"""Conservative aggregate of three read-only existing Quote-product UI checks.

Evidence is from an existing saved Quotation, NOT a new Quote request. A
historical Quote line's price or displayed process names can be a reusable
UI reference but never certify a current Product2/PricebookEntry catalog ID,
price, currency, Quote configuration, or permission to Save.
"""
import argparse
import json
from pathlib import Path

REQUIRED_CHECKS=frozenset({
    "saved_quotation_name_matches",
    "saved_total_krw_239250",
    "saved_list_price_krw_217500",
    "saved_coop_ts_yoo",
    "product_present",
    "two_processes_package1",
    "process_NovaSeq Reagent Kit (500 Cycles)",
    "process_Data quality control",
    "process_AliCloud",
    "no_edit_modal_open",
})


def reference_only_audit(rounds):
    if not isinstance(rounds,list):
        raise ValueError("INVALID_READBACK_EVIDENCE")
    results={item.get("round"):item for item in rounds if isinstance(item,dict)}
    valid=(len(rounds)==3 and set(results)=={1,2,3})
    if valid:
        for item in rounds:
            checks=item.get("checks")
            if (item.get("mode")!="READ_ONLY" or item.get("save_clicked") is not False
                    or item.get("status")!="PASS" or not isinstance(checks,dict)
                    or set(checks)!=REQUIRED_CHECKS
                    or not all(x is True for x in checks.values())):
                valid=False
                break
    return {
        "status":"HISTORICAL_QUOTE_PRODUCT_REFERENCE_VERIFIED" if valid else
                 "HOLD_HISTORICAL_PRODUCT_READBACK_UNCONFIRMED",
        "historical_readback_rounds":3 if valid else 0,
        "same_historical_quote_rechecked":valid,
        "saved_line_and_process_display_confirmed":valid,
        "current_product_catalog_id_verified":False,
        "current_pricebook_entry_id_verified":False,
        "current_quote_price_verified":False,
        "new_product_creation_permitted":False,
        "crm_save_allowed":False,
        "salesforce_writes":0,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default=str(Path.home()/".sfdc_desktop"/
                            "quote_product_pack_three_readonly_rounds_PRIVATE.json"))
    a=p.parse_args()
    source=Path(a.source).resolve()
    allowed=(Path.home()/".sfdc_desktop").resolve()
    if allowed not in source.parents:
        raise SystemExit("HOLD_SOURCE_MUST_REMAIN_PRIVATE")
    data=json.loads(source.read_text(encoding="utf-8-sig"))
    print(json.dumps(reference_only_audit(data),sort_keys=True))


if __name__=="__main__":
    main()
