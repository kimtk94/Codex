"""SFDC native Source Quote -> Product -> Process evidence reconciliation.

Pure (no HTTP, Salesforce writes, or customer data in repository). The
authenticated laptop reader supplies GET-only native IDs and 2026 KRW rows.
The output is an evidence snapshot, NEVER a Salesforce Save approval.

Important: Quotation_Process__c.Process_ID__c short codes (GY*/PR*) and
Report Process-YYYY-* IDs are different namespaces. Map by a unique exact
original process name within the already matched QD product and preserve
both IDs; never treat source child IDs as master IDs.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import re

NATIVE = re.compile(r"^[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?$")
REPORT = re.compile(r"^Process-[A-Za-z0-9-]{8,64}$")
QD = re.compile(r"^QD-\d{3,}$")
MONEY = re.compile(r"^(0|[1-9]\d*)(?:\.\d{1,2})?$")


def _krw(x):
    if isinstance(x, bool):
        return None
    text = str(x).replace(",", "").strip()
    if not MONEY.fullmatch(text):
        return None
    try:
        d = Decimal(text)
        return d if d.is_finite() and d == d.to_integral_value() else None
    except InvalidOperation:
        return None


def _hold(codes, records=None):
    return {
        "status": "HOLD_NATIVE_QUOTE_SOURCE",
        "reason_codes": sorted(set(codes)),
        "source_processes": records or [],
        "native_source_verified": False,
        "native_source_snapshot_complete": False,
        "new_quotation_price_approval": False,
        "save_permitted": False,
        "crm_writes": 0,
    }


def audit_source_bundle(queue, bundle, terms):
    errors=[]
    if not all(isinstance(x,dict) for x in (queue,bundle,terms)):
        return _hold(["SOURCE_INPUT_MISSING"])
    ref=queue.get("canonical",{}).get("reference",{})
    proposed=queue.get("canonical",{}).get("proposed",{})
    products=proposed.get("products")
    if not isinstance(products,list) or len(products)!=1 or not isinstance(products[0],dict):
        return _hold(["EXPECTED_SINGLE_PRODUCT_QUOTE"])
    p=products[0]
    product=bundle.get("product",{})
    old_ref=ref.get("sourceQuoteId")
    if not (isinstance(old_ref,str) and old_ref.startswith("a0P") and NATIVE.fullmatch(old_ref)
            and bundle.get("source_quotation_id")==old_ref):
        errors.append("ORIGINAL_QUOTATION_ID_MISMATCH")
    old_oppo=ref.get("opportunityId")
    if not (isinstance(old_oppo,str) and old_oppo.startswith("006") and NATIVE.fullmatch(old_oppo)
            and bundle.get("source_opportunity_id")==old_oppo):
        errors.append("ORIGINAL_OPPORTUNITY_ID_MISMATCH")
    if terms.get("proposed_exact_name")!=proposed.get("name") or (
        bundle.get("new_opportunity_name")!=proposed.get("name")
    ):
        errors.append("NAME_MUST_BE_EXACTLY_PRESERVED")
    if terms.get("approved_terms",{}).get("price_approved_by_operator") is not True:
        errors.append("NEW_KRW_PRICE_NOT_APPROVED")
    source_net=_krw(bundle.get("quote_net_krw"))
    source_gross=_krw(bundle.get("quote_gross_krw"))
    approved_net=_krw(terms.get("approved_terms",{}).get("net_krw"))
    approved_gross=_krw(terms.get("approved_terms",{}).get("gross_krw"))
    if (None in (source_net,source_gross,approved_net,approved_gross) or
        source_net!=approved_net or
        source_gross!=approved_gross or source_gross!=source_net*Decimal("1.10")):
        errors.append("NEW_AND_SOURCE_KRW_TOTALS_MISMATCH")
    if product.get("source_reference_product_id")!=p.get("id") or (
        not QD.fullmatch(str(p.get("id") or ""))
    ):
        errors.append("SOURCE_QD_PRODUCT_ID_MISMATCH")
    native_product=product.get("native_product_id")
    native_quote_product=product.get("native_quotation_product_id")
    if not (isinstance(native_product,str) and native_product.startswith("01t") and
            NATIVE.fullmatch(native_product) and
            isinstance(native_quote_product,str) and
            NATIVE.fullmatch(native_quote_product)):
        errors.append("PRODUCT_MASTER_OR_SOURCE_QUOTE_PRODUCT_ID_INVALID")
    expected_names=p.get("processNames")
    report_ids=p.get("processIds")
    if (not isinstance(expected_names,list) or not isinstance(report_ids,list) or
        len(expected_names)!=len(report_ids) or len(expected_names)!=4 or
        len(set(expected_names))!=4 or len(set(report_ids))!=4 or
        not all(isinstance(n,str) and n.strip() for n in expected_names) or
        not all(isinstance(pid,str) and REPORT.fullmatch(pid) for pid in report_ids)):
        return _hold(errors+["ORIGINAL_REPORT_PROCESS_MANIFEST_INVALID"])
    original=dict(zip(expected_names,report_ids))
    source_rows=bundle.get("processes")
    if not isinstance(source_rows,list) or len(source_rows)!=4:
        return _hold(errors+["NATIVE_QUOTATION_PROCESS_ROW_COUNT_MISMATCH"])
    records=[]
    seen=set()
    subtotal=Decimal(0)
    samples_rate=Decimal(0)
    fixed_rate=Decimal(0)
    ali_cloud_rows=[]
    for row in source_rows:
        if not isinstance(row,dict):
            errors.append("NATIVE_PROCESS_ROW_INVALID")
            continue
        name=row.get("name")
        native_id=row.get("native_id")
        process_master=row.get("process_master_id")
        parent=row.get("native_quotation_product_id")
        if not (isinstance(name,str) and name in original and name not in seen):
            errors.append("NATIVE_PROCESS_NAME_NOT_UNIQUE_OR_UNKNOWN")
            continue
        seen.add(name)
        if not (isinstance(native_id,str) and native_id.startswith("a0L") and NATIVE.fullmatch(native_id)
                and isinstance(process_master,str) and process_master.startswith("a0E") and NATIVE.fullmatch(process_master)
                and parent==native_quote_product):
            errors.append("NATIVE_PROCESS_MASTER_ID_OR_PARENT_UNVERIFIED")
        qty=_krw(row.get("quantity"))
        rate=_krw(row.get("unit_price_krw"))
        amount=_krw(row.get("net_krw"))
        if None in (qty,rate,amount) or qty<=0 or qty*rate!=amount:
            errors.append("NATIVE_PROCESS_QUANTITY_RATE_TOTAL_INVALID")
        else:
            subtotal+=amount
            if name!="Data release":
                if qty!=_krw(p.get("samples")):
                    errors.append("PROCESS_SAMPLE_COUNT_INCONSISTENT")
                samples_rate+=rate
            else:
                fixed_rate+=amount
        if row.get("currency")!="KRW":
            errors.append("NATIVE_PROCESS_NOT_KRW")
        if name!="Data release" and row.get("pack")!="Package1":
            errors.append("PACK_MISMATCH")
        if name=="Data release" and qty!=Decimal(1):
            errors.append("DATA_RELEASE_QUANTITY_INVALID")
        if row.get("process_type")=="AliCloud":
            ali_cloud_rows.append(name)
        records.append({
          "name":name,"report_process_id":original[name],
          "source_native_quotation_process_id":native_id,
          "native_process_master_id":process_master,
          "source_native_quotation_product_id":parent,
          "process_type":row.get("process_type"),
          "quantity":row.get("quantity"),
          "unit_price_krw":row.get("unit_price_krw"),
          "total_krw":row.get("net_krw"),
          "pack":row.get("pack"),
          "data_size":row.get("data_size"),
          "data_unit":row.get("data_unit"),
        })
    if seen!=set(original):
        errors.append("NATIVE_REPORT_PROCESS_COVERAGE_MISMATCH")
    if source_net is not None and subtotal!=source_net:
        errors.append("NATIVE_PROCESS_TOTAL_NOT_SOURCE_QUOTE_NET")
    if _krw(p.get("sampleUnitKrw"))!=samples_rate:
        errors.append("SAMPLE_UNIT_RATE_NOT_RECONCILED")
    fixed=p.get("fixedProcessLines") or []
    if len(fixed)!=1 or not isinstance(fixed[0],dict) or (
        fixed[0].get("processName")!="Data release" or
        fixed[0].get("processId")!=original.get("Data release") or
        _krw(fixed[0].get("netKrw"))!=fixed_rate
    ):
        errors.append("FIXED_DATA_RELEASE_PRICE_MISMATCH")
    # The user approved 260,000 KRW including the 30k Data release, but
    # separately said to exclude AliCloud. Salesforce calls this Process Type
    # "AliCloud". A source match does not resolve that policy ambiguity.
    if terms.get("approved_terms",{}).get("alicloud")=="EXCLUDE" and ali_cloud_rows:
        errors.append("ALICLOUD_EXCLUDED_BUT_SOURCE_HAS_ALICLOUD_TYPED_PROCESS")
    if errors:
        held=_hold(errors,records)
        # Original SFDC Process IDs/rates can be completely verified while
        # the separately approved AliCloud business condition remains HOLD.
        # Expose these two independent facts; do not promote to Save readiness.
        if set(errors)=={"ALICLOUD_EXCLUDED_BUT_SOURCE_HAS_ALICLOUD_TYPED_PROCESS"}:
            held["native_source_verified"]=True
            held["native_source_snapshot_complete"]=True
        return held
    return {
        "status":"NATIVE_SOURCE_LINES_VERIFIED_NOT_SAVE_APPROVED",
        "reason_codes":[],
        "source_processes":records,
        "native_source_verified":True,
        "native_source_snapshot_complete":True,
        "new_quotation_price_approval":False,
        "save_permitted":False,
        "crm_writes":0,
    }
