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
    """Operational summary, NOT a fake editable markdown grid.

    A real edit/popup route now exists in 00 영업 홈 > 바로가기 > 바로 편집.
    Avoid raw pseudo-checkboxes and markdown links that Feishu renders inert.
    """
    if not link.startswith("https://ocnz4cb25scn.feishu.cn/base/") or "&view=vew" not in link:
        raise SafeError("QUOTE_PREVIEW_INVALID_EDITABLE_LINK")
    if len(rows)>MAX_ENTRIES:
        raise SafeError("QUOTE_PREVIEW_TOO_MANY_RECORDS_REFUSE_SILENT_TRUNCATION")
    headings=[
        "## 실제 Quote 검토 · 편집 방법",
        "**이 대시보드의 텍스트 요약은 읽기 전용입니다. 체크박스나 셀을 여기서 수정할 수 없습니다.**",
        "**수정하려면:** 00 영업 홈 → 바로가기 → WEEKLY_TREND 행 → 파란색 '✎ Weekly Quote 편집 · 합산 제외' 클릭",
        "해당 버튼은 실제 Feishu 'Weekly Quote Review'의 최근 5주 그리드를 엽니다.",
        "그리드에서 '합산 제외' 체크박스를 수정하거나 Quote Name 셀 오른쪽의 아이콘으로 상세 팝업을 열어 수정할 수 있습니다.",
        "Active 확인 없는 Quote는 체크를 해제해도 합산되지 않습니다. 금액은 예상 견적이며 실제 Revenue가 아닙니다.",
        "",
        "### 최근 5주 원본 건수 (읽기 전용 요약)",
    ]
    grouped=collections.defaultdict(list)
    for week,_,_,fields in rows:
        grouped[week].append(fields)
    for week in sorted(grouped,reverse=True):
        group=grouped[week]
        included=sum(val(f,"합산 상태")=="INCLUDED" for f in group)
        excluded=sum(checkbox(f.get("합산 제외")) for f in group)
        headings.append(
            "- "+week+" 시작: 승인 "+str(len(group))+"건 / 합산 "+str(included)+
            "건 / 체크 제외 "+str(excluded)+"건"
        )
    headings.append("")
    headings.append("편집 후 반영 여부는 Weekly Quote KPI의 다음 원천 동기화 결과로 확인합니다.")
    result="\\n".join(headings)
    if len(result)>MAX_TEXT:
        raise SafeError("QUOTE_PREVIEW_TEXT_LIMIT_EXCEEDED")
    return result

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
