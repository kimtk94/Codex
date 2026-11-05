#!/usr/bin/env python3
"""One-login, multi-check Salesforce Lookup audit. Never clicks Save."""
import argparse,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,Error as PWError
from runner import check_url,PROFILE
from lookup_preflight import prepare_lookup,find_input
from lookup_exact_option_probe import select,selected_state

def window_inventory(ctx):
    rows=[]
    for i,page in enumerate(ctx.pages):
        if page.is_closed():continue
        frames=0
        labels=0
        for frame in page.frames:
            frames+=1
            try:
                labels+=frame.evaluate("""() => {
                  const visited=new Set();
                  let n=0;
                  function scan(root) {
                    if(!root||visited.has(root))return;
                    visited.add(root);
                    for(const el of root.querySelectorAll('*')){
                      if(el.shadowRoot)scan(el.shadowRoot);
                      if(el.matches('label') && /^(Account Name|Main Contact)\\s*\\*?$/.test((el.textContent||'').trim()))n++;
                    }
                  }
                  scan(document);return n;
                }""")
            except PWError:pass
        rows.append({"tab_index":i,"origin":page.url.split("/")[2] if "://" in page.url else "",
                     "frame_count":frames,"lookup_label_count":labels})
    return rows

def focus_and_maximize(page):
    """CDP window bounds verification; never claim max without readback."""
    result={"front":False,"maximized":False,"method":"CDP"}
    page.bring_to_front()
    result["front"]=True
    session=page.context.new_cdp_session(page)
    try:
        window=session.send("Browser.getWindowForTarget")
        wid=window["windowId"]
        result["window_id"]=wid
        before=session.send("Browser.getWindowBounds",{"windowId":wid})["bounds"]
        result["before_state"]=before.get("windowState")
        if before.get("windowState") in ("fullscreen","minimized"):
            session.send("Browser.setWindowBounds",{"windowId":wid,"bounds":{"windowState":"normal"}})
        session.send("Browser.setWindowBounds",{"windowId":wid,"bounds":{"windowState":"maximized"}})
        after=session.send("Browser.getWindowBounds",{"windowId":wid})["bounds"]
        result["after_state"]=after.get("windowState")
        result["maximized"]=after.get("windowState")=="maximized"
        if not result["maximized"]:
            result["error"]="CDP_MAXIMIZE_NOT_CONFIRMED"
    except (PWError,KeyError) as exc:
        result["error_type"]=type(exc).__name__
    finally:
        session.detach()
    return result

def audit(ctx,label,name):
    d={"input":"NOT_FOUND","search":"NOT_RUN","selection":"NOT_RUN"}
    loc,status=find_input(ctx,label)
    if loc is None:
        d["input"]=status
    else:
        d["input"]="FOUND"
    d["pre_existing_selected"]=selected_state(ctx,label,name)
    # Existing select() performs search affordance, exact candidate click and pill check.
    d["selection"]=select(ctx,label,name)
    d["post_selection"]=selected_state(ctx,label,name)
    return d

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    p.add_argument("--draft",required=True)
    p.add_argument("--cdp-url",default="http://127.0.0.1:9222")
    p.add_argument("--output",default="")
    a=p.parse_args()
    check_url(a.url)
    values=prepare_lookup(json.loads(Path(a.draft).read_text(encoding="utf-8-sig")))
    with sync_playwright() as pw:
        browser=pw.chromium.connect_over_cdp(a.cdp_url) if a.cdp_url else None
        ctx=browser.contexts[0] if browser and browser.contexts else pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),headless=False,channel="chrome")
        attached=bool(browser and browser.contexts)
        try:
            if not attached:
                page=ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(a.url,wait_until="domcontentloaded")
            input("Use authenticated Chrome; open New Opportunity, then Enter ONCE: ")
            inventory=window_inventory(ctx)
            print("Chrome tabs / New Opportunity label counts:",json.dumps(inventory,ensure_ascii=False))
            # Salesforce form title is already confirmed in CDP, while labels can be async.
            matches=[]
            for item in inventory:
                p=ctx.pages[item["tab_index"]]
                try:
                    title=p.title().lower()
                except PWError:
                    title=""
                if ("new opportunity" in title and
                    (item["origin"].endswith("force.com") or item["origin"].endswith("salesforce.com"))):
                    matches.append(item)
            if len(matches)!=1:
                matches=[x for x in inventory if x["lookup_label_count"]>=2 and
                         (x["origin"].endswith("force.com") or x["origin"].endswith("salesforce.com"))]
            if len(matches)!=1:
                report={"version":"lookup-batch-audit-v2","failure":"NO_UNIQUE_NEW_OPPORTUNITY_WINDOW",
                        "tabs":inventory,"fields":{},"save_clicked":False,"both_verified":False}
                path=Path(a.output) if a.output else Path(a.draft).with_name("lookup_batch_audit.json")
                path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                print(json.dumps(report,ensure_ascii=False,indent=2))
                raise SystemExit("Open exactly ONE New Opportunity form in the CDP Chrome; no input attempted.")
            active=ctx.pages[matches[0]["tab_index"]]
            focus=focus_and_maximize(active)
            print("Selected target tab:",matches[0]["tab_index"],"focus/maximize:",focus)
            report={"version":"lookup-batch-audit-v2","target_tab":matches[0]["tab_index"],
                    "tabs":inventory,"fields":{},"save_clicked":False}
            for label in ("Account Name","Main Contact"):
                try:report["fields"][label]=audit(ctx,label,values[label])
                except Exception as e:
                    report["fields"][label]={"error_type":type(e).__name__,"message":str(e)[:200]}
                print(label,":",json.dumps(report["fields"][label],ensure_ascii=False))
            report["both_verified"]=all(report["fields"].get(label,{}).get("post_selection",{}).get("verified") is True
                for label in ("Account Name","Main Contact"))
            path=Path(a.output) if a.output else Path(a.draft).with_name("lookup_batch_audit.json")
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(report,ensure_ascii=False,indent=2))
            print("REPORT:",path)
            input("Inspect selected values in browser; Enter to finish: ")
        finally:
            if not attached:ctx.close()

if __name__=="__main__":main()
