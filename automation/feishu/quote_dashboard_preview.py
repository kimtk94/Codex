#!/usr/bin/env python3
"""Read-only, source-derived Quote list on the Weekly native dashboard.

Dashboard CLI does not support creating interactive Grid view blocks.
Use actual Feishu records for preview and link to the same editable View.
"""
import collections
import re
from qq_mail_ingest import SafeError,auth,list_all,plain_field
from setup_sales_web import list_views
from sales_native_home import table_map,target_path
from weekly_quote_review import checkbox

TABLE="Weekly Quote Review"
VIEW="그래프 연동 · 최근 5주 검토"
BLOCK_NAME="실제 Quote 목록 · 최근 5주 (체크 상태)"
WINDOW="RECENT_4_PLUS_CURRENT"
MAX_ENTRIES=90
MAX_TEXT=26000

def val(fields,key,limit=85):
    s=plain_field(fields.get(key)).replace("|","/").replace("\r"," ").replace("\n"," ").strip()
    return s[:limit]+("…" if len(s)>limit else "") if s else "-"

def extract(records):
    seen=set()
    rows=[]
    for item in records:
        f=item.get("fields") or {}
        if val(f,"Chart Window")!=WINDOW:
            continue
        key=val(f,"Source Key")
        if not key.startswith("QUOTE_REVIEW:a0P") or key in seen:
            raise SafeError("QUOTE_PREVIEW_DUPLICATE_OR_MISSING_ID")
        seen.add(key)
        week=val(f,"Week Start")
        if not re.fullmatch(r"20\d\d-\d\d-\d\d",week):
            raise SafeError("QUOTE_PREVIEW_INVALID_WEEK")
        rows.append((week,val(f,"Approval KST",28),key,f))
    if not rows:
        raise SafeError("QUOTE_PREVIEW_NO_RECENT_RECORDS")
    rows.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True)
    if len({x[0] for x in rows})>5:
        raise SafeError("QUOTE_PREVIEW_WINDOW_OVER_FIVE_WEEKS")
    return rows

def render(rows,link):
    if not link.startswith("https://ocnz4cb25scn.feishu.cn/base/") or "&view=vew" not in link:
        raise SafeError("QUOTE_PREVIEW_INVALID_EDITABLE_LINK")
    labels=[
        "## 실제 Quote 목록 · 최근 완료 4주 + 진행 중 1주",
        "**아래는 실제 Feishu Quote Review 레코드의 읽기 전용 미리보기입니다.**",
        "**체크하려면 [견적 목록 열기 · 합산 제외 체크박스 편집]("+link+")로 이동하세요.**",
        "체크 상태는 ☑ 제외 / ☐ 미체크. Inactive는 미체크여도 합산에서 제외됩니다.",
        "합산 판단을 위해 기관·서비스·샘플 수·금액 근거·Active 상태를 확인하세요.",
        "견적금액은 참고용 예상금액이며 실제 Revenue가 아닙니다. 증빙 없는 금액은 - 입니다.",
    ]
    grouped=collections.defaultdict(list)
    for row in rows:
        grouped[row[0]].append(row[3])
    for week in sorted(grouped,reverse=True):
        weekrows=grouped[week]
        included=sum(val(f,"합산 상태")=="INCLUDED" for f in weekrows)
        manual=sum(checkbox(f.get("합산 제외")) for f in weekrows)
        labels.extend(["",f"### {week} 시작 · 승인 {len(weekrows)}건 · 합산 {included}건 · 체크 제외 {manual}건",
                       "| 제외 | Quote / 기관 | 서비스·공정 / 샘플수 | 상태 / 참고금액 |",
                       "|:---:|---|---|---|"])
        for f in weekrows:
            marker="☑" if checkbox(f.get("합산 제외")) else "☐"
            title=val(f,"Quote Name",58)
            account=val(f,"기관",32)
            service=val(f,"서비스·공정",64)
            qty=val(f,"샘플수(공정별)",30)
            active=val(f,"SFDC IsActive",20)
            status=val(f,"합산 상태",20)
            amount=val(f,"참고 견적 USD",23)
            labels.append(f"| {marker} | {title} / {account} | {service} / {qty} | Active={active}, {status} / USD {amount} |")
    if len(rows)>MAX_ENTRIES:
        raise SafeError("QUOTE_PREVIEW_TOO_MANY_RECORDS_REFUSE_SILENT_TRUNCATION")
    out="\n".join(labels)
    if len(out)>MAX_TEXT:
        raise SafeError("QUOTE_PREVIEW_TEXT_LIMIT_EXCEEDED")
    return out

def read_preview():
    token,root=auth()
    catalog=table_map(token,root)
    tid=catalog.get(TABLE)
    if not tid:
        raise SafeError("QUOTE_PREVIEW_TABLE_MISSING")
    path=target_path(root,tid)
    view=list_views(token,path).get(VIEW)
    if not view:
        raise SafeError("QUOTE_PREVIEW_EDITABLE_VIEW_MISSING")
    link="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table="+tid+"&view="+view
    records=list_all(path+"/records",token,"weekly_quote_dashboard_preview")
    rows=extract(records)
    result=render(rows,link)
    print("QUOTE_PREVIEW_SOURCE_PASS rows="+str(len(rows))+
          " weeks="+str(len(set(x[0] for x in rows)))+
          " latest="+rows[0][0]+" edits_to_source=0",flush=True)
    print("QUOTE_PREVIEW_EDITABLE_URL="+link,flush=True)
    return result
