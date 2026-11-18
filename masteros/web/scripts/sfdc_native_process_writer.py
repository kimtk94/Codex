"""Exact native Salesforce Quotation Product process price writer.

Only the *new*, not yet saved quotation is editable. The pricing matrix is
validated from a live, selected source Quote and checked against the native
new-Quote form before a Product Save click. Never use Standard Price in place
of customer's quoted Unit Price; preserve Pack and 100-Gb AliCloud quantity.
"""
import math
import re

HEADERS=["","","Pack No.","Process Name","Process Type","Sample Number",
         "Data Size","Data Unit","Unit Price","Standard Price","Note","",""]
PRICE_ID=re.compile(r"^[A-Za-z0-9() .,+/\-]{1,160}$")
def positive_int(v):return type(v) is int and 1<=v<=100000
def integer_money(v):return type(v) is int and 0<=v<=1000000000

def validated_price_plan(lines,samples,gb,net):
    """Fail closed against exact native source Pack, quantity, price and net."""
    if (not isinstance(lines,list) or not 2<=len(lines)<=25 or
        not positive_int(samples) or not isinstance(gb,(int,float)) or
        isinstance(gb,bool) or not math.isfinite(gb) or not 0<gb<=100000 or
        not integer_money(net) or net<=0):
        raise ValueError("NATIVE_PRICE_PLAN_INVALID")
    out=[]
    seen=set()
    noncloud_packs=set()
    clouds=0
    for raw in lines:
        if not isinstance(raw,dict):raise ValueError("NATIVE_PROCESS_ROW_INVALID")
        typ=raw.get("processType")
        name=raw.get("processName")
        qty=raw.get("quantity")
        rate=raw.get("unitPriceKrw")
        cloud=raw.get("isCloud")
        pack=raw.get("packNo")
        if (not isinstance(typ,str) or not PRICE_ID.fullmatch(typ) or
            not isinstance(name,str) or not PRICE_ID.fullmatch(name) or
            type(cloud) is not bool or not positive_int(qty) or
            not integer_money(rate) or not isinstance(pack,str) or
            len(pack)>100):
            raise ValueError("NATIVE_PROCESS_ROW_INVALID")
        key=(typ,name)
        if key in seen:raise ValueError("NATIVE_PROCESS_DUPLICATE_KEY")
        seen.add(key)
        expected=math.ceil(samples*gb/100) if cloud else samples
        if qty!=expected:raise ValueError("NATIVE_PROCESS_QTY_MISMATCH")
        if cloud:clouds+=1
        else:
            if not pack:raise ValueError("NATIVE_PROCESS_PACK_MISSING")
            noncloud_packs.add(pack)
        out.append({"processType":typ,"processName":name,"quantity":qty,
                    "unitPriceKrw":rate,"isCloud":cloud})
    if len(noncloud_packs)!=1 or clouds!=1:
        raise ValueError("NATIVE_PACK_OR_CLOUD_NOT_UNIQUE")
    if sum(r["quantity"]*r["unitPriceKrw"] for r in out)!=net:
        raise ValueError("NATIVE_PROCESS_NET_MISMATCH")
    return {"lines":out,"samples":samples,"dataSize":gb,"expectedNet":net,
            "cloudUnits":math.ceil(samples*gb/100),
            "productCount":1,"sourcePackVerified":True}


def verify_native_matrix(expected,matrix):
    """Pure post-edit readback; never trust UI success or a selected Product alone."""
    from sfdc_record_catalog import _source_modal_money,_source_modal_qty
    if not isinstance(matrix,dict) or matrix.get("headers")!=HEADERS:
        raise ValueError("NATIVE_MATRIX_SCHEMA_CHANGED")
    rows=matrix.get("rows")
    if not isinstance(rows,list) or len(rows)!=len(expected["lines"]):
        raise ValueError("NATIVE_MATRIX_ROW_COUNT_MISMATCH")
    observed={}
    packs=set()
    for row in rows:
        if not isinstance(row,list) or len(row)!=len(HEADERS):
            raise ValueError("NATIVE_MATRIX_ROW_INVALID")
        typ=str(row[3]["text"]).strip()
        name=str(row[4]["text"]).strip()
        key=(typ,name)
        if key in observed:raise ValueError("NATIVE_MATRIX_DUPLICATE_PROCESS")
        pack=str(row[2]["text"]).strip()
        qty=_source_modal_qty(row[5].get("value"))
        price=_source_modal_money(row[8].get("value"))
        size=float(str(row[6].get("value")).replace(",",""))
        if not math.isfinite(size) or size<=0:
            raise ValueError("NATIVE_MATRIX_SIZE_INVALID")
        observed[key]={"quantity":qty,"unitPriceKrw":price,
                       "packNo":pack,"dataSize":size}
    amount=0
    for line in expected["lines"]:
        key=(line["processType"],line["processName"])
        item=observed.get(key)
        if item is None:raise ValueError("NATIVE_MATRIX_PROCESS_MISMATCH")
        if item["quantity"]!=line["quantity"] or item["unitPriceKrw"]!=line["unitPriceKrw"]:
            raise ValueError("NATIVE_MATRIX_PRICE_QTY_MISMATCH")
        if not line["isCloud"]:
            if abs(item["dataSize"]-expected["dataSize"])>1e-6:
                raise ValueError("NATIVE_MATRIX_DATA_SIZE_MISMATCH")
            if not item["packNo"]:raise ValueError("NATIVE_MATRIX_PACK_UNSET")
            packs.add(item["packNo"])
        amount+=item["quantity"]*item["unitPriceKrw"]
    if len(packs)!=1:raise ValueError("NATIVE_MATRIX_PACK_SPLIT")
    if amount!=expected["expectedNet"]:
        raise ValueError("NATIVE_MATRIX_SUM_MISMATCH")
    # Source Salesforce Quote may include a separate Fee: it is unsupported
    # until the actual new-Quote Fee writer is verified.
    total=_source_modal_money(matrix.get("total"))
    if total!=amount:raise ValueError("NATIVE_MATRIX_TOTAL_MISMATCH")
    return {"status":"PASS","net":amount,"samplePackCount":len(packs),
            "sourceProcessCount":len(expected["lines"]),
            "cloudUnits":expected["cloudUnits"],"priceVerified":True}


def snapshot_matrix(dialog):
    table=dialog.locator("table").filter(has_text="Pack No.").filter(has_text="Unit Price")
    if table.count()!=1:raise ValueError("NEW_QUOTE_PRICE_MATRIX_NOT_UNIQUE")
    cells=table.evaluate("""node=>[...node.querySelectorAll('tr')].map(tr=>
      [...tr.querySelectorAll('th,td')].map(c=>({
        text:(c.innerText||'').trim().replace(/\\s+/g,' '),
        value:c.querySelector('input[type=text]')?.value??null
      })))""")
    summary=dialog.locator("table").filter(has_text="Sales Price").filter(has_text="List Price")
    if summary.count()!=1:raise ValueError("NEW_QUOTE_SUMMARY_NOT_UNIQUE")
    subtotals=summary.evaluate("""node=>[...node.querySelectorAll('tr')].map(tr=>
      [...tr.querySelectorAll('th,td')].map(c=>(c.innerText||'').trim().replace(/\\s+/g,' ')))""")
    if len(subtotals)!=2 or subtotals[0]!=["Total","Sales Price","List Price"]:
        raise ValueError("NEW_QUOTE_SUMMARY_CHANGED")
    return {"headers":[c["text"] for c in cells[0]],"rows":cells[1:],
            "total":subtotals[1][0]}


def fill_exact_money(control,value):
    """Lightning amount fields append without explicit select-all/Backspace."""
    from sfdc_record_catalog import _source_modal_money
    if control.count()!=1 or not control.is_enabled():
        raise ValueError("NEW_QUOTE_MONEY_CONTROL_NOT_EDITABLE")
    control.click(timeout=5000)
    control.press("ControlOrMeta+A",timeout=3000)
    control.press("Backspace",timeout=3000)
    control.type(str(value),delay=20,timeout=9500)
    control.press("Tab",timeout=3000)
    if _source_modal_money(control.input_value())!=value:
        raise ValueError("NEW_QUOTE_MONEY_INPUT_READBACK_MISMATCH")


def set_process_prices_in_unsaved_modal(page,dialog,plan):
    """All UI edits remain UNSAVED until native source-matrix parity PASS."""
    from sfdc_record_catalog import _source_modal_money,_source_modal_qty
    table=dialog.locator("table").filter(has_text="Pack No.").filter(has_text="Unit Price")
    table.wait_for(state="visible",timeout=19000)
    if table.count()!=1:raise ValueError("NEW_QUOTE_MATRIX_AMBIGUOUS")
    actual=table.locator("tr")
    for _ in range(40):
        if actual.count()==len(plan["lines"])+1:break
        page.wait_for_timeout(250)
    if actual.count()!=len(plan["lines"])+1:
        raise ValueError("NEW_QUOTE_MATRIX_ROWS_UNAVAILABLE")
    raw=snapshot_matrix(dialog)
    if raw["headers"]!=HEADERS:raise ValueError("NEW_QUOTE_MATRIX_SCHEMA_CHANGED")
    # The source and new Quote may reorder rows. Identity is exact pair
    # (Process Name column, Process Type column), never row number alone.
    by_key={}
    for i,row in enumerate(raw["rows"],1):
        key=(row[3]["text"].strip(),row[4]["text"].strip())
        if key in by_key:raise ValueError("NEW_QUOTE_DUPLICATE_PROCESS")
        by_key[key]=i
    expected_keys={(x["processType"],x["processName"]) for x in plan["lines"]}
    if set(by_key)!=expected_keys:
        raise ValueError("NEW_QUOTE_PROCESS_SELECTION_MISMATCH")
    # Quantity/price first; pack selection second, because Lightning may rerender.
    for row in plan["lines"]:
        i=by_key[(row["processType"],row["processName"])]
        target=actual.nth(i).locator("th,td")
        if row["isCloud"]:
            cloudqty=target.nth(5).locator('input[type="text"]')
            fill_exact_money(cloudqty,row["quantity"])
        else:
            qty=target.nth(5).locator('input[type="text"]')
            if qty.count()!=1 or _source_modal_qty(qty.input_value())!=row["quantity"]:
                raise ValueError("NEW_QUOTE_SAMPLE_QTY_MISMATCH")
        rate=target.nth(8).locator('input[type="text"]')
        fill_exact_money(rate,row["unitPriceKrw"])
    before=snapshot_matrix(dialog)
    no_pack=[]
    for line in plan["lines"]:
        if line["isCloud"]:continue
        i=by_key[(line["processType"],line["processName"])]
        if not before["rows"][i-1][2]["text"].strip():no_pack.append(i)
    if no_pack:
        # Only automatically pack if ALL biological process rows initially
        # lack Pack. A partial/mixed state is ambiguous and must be reviewed.
        all_biological=sum(not x["isCloud"] for x in plan["lines"])
        if len(no_pack)!=all_biological:
            raise ValueError("NEW_QUOTE_PARTIAL_PACK_AMBIGUOUS")
        for i in no_pack:
            row=actual.nth(i)
            check=row.locator('input[type="checkbox"]')
            if check.count()!=1 or not check.is_enabled():
                raise ValueError("NEW_QUOTE_PACK_SELECT_NOT_VERIFIED")
            if not check.is_checked():check.check(timeout=5500)
        pack=dialog.get_by_text("Pack",exact=True)
        if pack.count()!=1 or not pack.is_enabled():
            raise ValueError("NEW_QUOTE_PACK_BUTTON_NOT_VERIFIED")
        pack.click(timeout=7000)
        page.wait_for_timeout(600)
    evidence=verify_native_matrix(plan,snapshot_matrix(dialog))
    return evidence
