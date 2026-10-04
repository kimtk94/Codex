#!/usr/bin/env python3
import argparse, datetime as dt, json, os, re, sqlite3
from collections import Counter, defaultdict
from pathlib import Path


def safe(v, fallback="Unknown"):
    v=re.sub(r'[\\/:*?"<>|]', '_', str(v or fallback).strip())
    return re.sub(r'\s+', ' ', v).strip(' .') or fallback


def fmt(v): return '-' if v in (None,'') else str(v).replace('\n',' ').strip()
def link(folder, title, label=None): return f"[[{folder}/{safe(title)}|{label or title}]]"


def note(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text('\n'.join(lines).rstrip()+'\n', encoding='utf-8'); tmp.replace(path)


def records(matrix):
    if not matrix: return []
    h=[str(x).strip() for x in matrix[0]]; out=[]
    for row in matrix[1:]:
        r={k:(row[i] if i<len(row) else None) for i,k in enumerate(h)}
        if any(v not in (None,'') for v in r.values()): out.append(r)
    return out


def snapshot(path):
    if not path or not path.exists(): return None
    d=json.loads(path.read_text(encoding='utf-8'))
    return {k:(records(d.get(k,[])) if k!='fetched_at' else d.get(k)) for k in ('project_dashboard','action_center','customer_360','fetched_at')}


def customer_guess(desc):
    if not desc: return 'Unknown Customer'
    parts=[x.strip() for x in desc.split('-') if x.strip()]
    for x in parts:
        if x.lower().startswith('prof.'): return x
    stop={'wbi','wobi','quantification','other','mrna-seq','mrnaseq','wgs','metagenome','amplicon','proteomics'}
    for x in reversed(parts):
        if x.lower().replace(' ','') not in stop and not re.search(r'\d',x) and re.fullmatch(r'[A-Za-z.]+',x) and len(x)>=5: return x
    return 'Unknown Customer'


def db_latest(con):
    q="""WITH r AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY project_id ORDER BY datetime(received_at) DESC,processed_at DESC,uid DESC) n FROM project_timeline WHERE COALESCE(TRIM(project_id),'')<>'') SELECT * FROM r WHERE n=1"""
    return [dict(x) for x in con.execute(q)]


def canonical(snap):
    if not snap: return None
    out=[]
    for r in snap['project_dashboard']:
        pid=str(r.get('project_id') or '').strip()
        if not pid or str(r.get('exclude') or '').upper() in {'TRUE','YES','1'}: continue
        yes=lambda v:str(v or '').strip().lower() in {'yes','true','1','y'}
        try: progress=int(float(r.get('progress_percent') or 0))
        except Exception: progress=0
        out.append(dict(project_id=pid,received_at=r.get('latest_email_at'),stage=r.get('current_stage') or 'Unclassified',progress_percent=progress,checkpoint=r.get('latest_checkpoint'),action_required=int(yes(r.get('latest_action_required')) or yes(r.get('attention'))),sample_count=r.get('latest_confirmed_samples') or r.get('received_samples'),planned_samples=r.get('planned_samples'),institution=r.get('institution') or 'Unknown Institution',service=r.get('service') or 'Other',project_description=r.get('project_description'),subject=r.get('latest_subject'),customer=r.get('customer_name') or 'Unknown Customer',attention_reason=r.get('attention_reason')))
    return out


def rows(con, sql, args=()): return [dict(x) for x in con.execute(sql,args)]


def build(db_path:Path, vault:Path, sheet_snapshot:Path|None=None):
    con=sqlite3.connect(str(db_path)); con.row_factory=sqlite3.Row
    snap=snapshot(sheet_snapshot); projects=canonical(snap) or db_latest(con)
    generated=dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec='seconds')
    src='CSS Project Dashboard + css_project_manager.sqlite3' if snap else 'css_project_manager.sqlite3'
    base=vault/'02_CSS'
    for x in ('Institutions','Customers','Projects','Services','Actions'): (base/x).mkdir(parents=True,exist_ok=True)
    (vault/'00_HOME').mkdir(parents=True,exist_ok=True)
    by_i,by_c,by_s=defaultdict(list),defaultdict(list),defaultdict(list)
    for p in projects:
        p['institution']=str(p.get('institution') or 'Unknown Institution').strip(); p['service']=str(p.get('service') or 'Other').strip()
        p['customer']=p.get('customer') or customer_guess(p.get('project_description'))
        by_i[p['institution']].append(p); by_c[p['customer']].append(p); by_s[p['service']].append(p)

    for p in projects:
        pid=p['project_id']; tl=rows(con,"SELECT received_at,stage,progress_percent,checkpoint,action_required,subject FROM project_timeline WHERE project_id=? ORDER BY datetime(received_at) DESC,processed_at DESC LIMIT 20",(pid,))
        inv=rows(con,"SELECT received_at,invoice_number,amount_krw,po_reference FROM tax_invoices WHERE project_id=? ORDER BY datetime(received_at) DESC",(pid,))
        total=sum(int(x.get('amount_krw') or 0) for x in inv)
        L=['---','type: css_project',f'project_id: {pid}',f'stage: "{fmt(p.get("stage"))}"',f'progress_percent: {int(p.get("progress_percent") or 0)}',f'action_required: {str(bool(p.get("action_required"))).lower()}',f'generated_at: "{generated}"',f'source: {src}','---','',f'# {pid}','','## Links','',f'- Institution: {link("02_CSS/Institutions",p["institution"])}',f'- Customer: {link("02_CSS/Customers",p["customer"])}',f'- Service: {link("02_CSS/Services",p["service"])}','','## Current status','',f'- Stage: **{fmt(p.get("stage"))}**',f'- Progress: **{int(p.get("progress_percent") or 0)}%**',f'- Action required: **{"YES" if p.get("action_required") else "No"}**',f'- Planned samples: {fmt(p.get("planned_samples"))}',f'- Latest sample count: {fmt(p.get("sample_count"))}',f'- Latest email: {fmt(p.get("received_at"))}',f'- Description: {fmt(p.get("project_description"))}',f'- Invoice total: {total:,} KRW','','## Recent timeline','','| Date | Stage | Progress | Action | Checkpoint | Subject |','|---|---|---:|---|---|---|']
        for x in tl: L.append(f'| {fmt(x.get("received_at"))} | {fmt(x.get("stage"))} | {int(x.get("progress_percent") or 0)}% | {"⚠️" if x.get("action_required") else ""} | {fmt(x.get("checkpoint"))} | {fmt(x.get("subject")).replace("|","/")} |')
        if inv:
            L += ['','## Invoices','','| Date | Invoice | Amount | PO |','|---|---|---:|---|']
            for x in inv: L.append(f'| {fmt(x.get("received_at"))} | {fmt(x.get("invoice_number"))} | {int(x.get("amount_krw") or 0):,} | {fmt(x.get("po_reference"))} |')
        note(base/'Projects'/f'{safe(pid)}.md',L)

    def index_notes(group, folder, kind, other):
        for name, ps in group.items():
            L=['---',f'type: css_{kind}',f'generated_at: "{generated}"',f'source: {src}','---','',f'# {name}','',f'- Projects: **{len(ps)}**',f'- Active: **{sum(int(x.get("progress_percent") or 0)<100 for x in ps)}**','','## Projects','',f'| Project | {other.title()} | Stage | Progress | Action |','|---|---|---|---:|---|']
            for p in sorted(ps,key=lambda x:x.get('received_at') or '',reverse=True):
                val=p[other]; target='Customers' if other=='customer' else ('Institutions' if other=='institution' else 'Services')
                L.append(f'| {link("02_CSS/Projects",p["project_id"])} | {link("02_CSS/"+target,val)} | {fmt(p.get("stage"))} | {int(p.get("progress_percent") or 0)}% | {"⚠️" if p.get("action_required") else ""} |')
            note(base/folder/f'{safe(name)}.md',L)
    index_notes(by_i,'Institutions','institution','customer'); index_notes(by_c,'Customers','customer','institution'); index_notes(by_s,'Services','service','institution')

    acts=[]
    if snap:
        closed={'완료','해결','종료','제외','closed','done','resolved'}
        acts=[r for r in snap['action_center'] if str(r.get('status') or '').strip().lower() not in closed]
        for a in acts:
            tid=str(a.get('task_id') or f"ACTION-{a.get('project_id') or 'unknown'}"); pid=str(a.get('project_id') or '').strip(); inst=a.get('institution') or 'Unknown Institution'; cust=a.get('customer_name') or 'Unknown Customer'; svc=a.get('service') or 'Other'
            L=['---','type: css_action',f'task_id: {tid}',f'status: "{fmt(a.get("status"))}"',f'priority: "{fmt(a.get("priority"))}"',f'due_date: "{fmt(a.get("due_date"))}"',f'generated_at: "{generated}"','source: CSS Action Center','---','',f'# {tid}','',f'- Project: {link("02_CSS/Projects",pid) if pid else "-"}',f'- Institution: {link("02_CSS/Institutions",inst)}',f'- Customer: {link("02_CSS/Customers",cust)}',f'- Service: {link("02_CSS/Services",svc)}',f'- Owner: {fmt(a.get("owner"))}',f'- Task type: {fmt(a.get("task_type"))}','','## Reason','',fmt(a.get('reason')),'','## Evidence','',fmt(a.get('evidence')),'','## Recommended action','',fmt(a.get('recommended_action')),'','## Reply draft — KO','',fmt(a.get('reply_draft_ko')),'','## Reply draft — EN','',fmt(a.get('reply_draft_en')),'','## Notes','',fmt(a.get('notes')),'','## Source','',f'- Source link: {fmt(a.get("source_link"))}',f'- Evidence UID: {fmt(a.get("evidence_uid"))}',f'- Latest email: {fmt(a.get("latest_email_at"))}',f'- Updated at: {fmt(a.get("updated_at"))}']
            note(base/'Actions'/f'{safe(tid)}.md',L)
    else: acts=[p for p in projects if p.get('action_required')]
    Q=['---','type: css_action_index',f'generated_at: "{generated}"',f'source: {"CSS Action Center" if snap else "css_project_manager.sqlite3"}','---','','# CSS Action Queue','']
    if snap:
        Q += ['| Priority | Due | Task | Project | Institution | Type | Reason |','|---|---|---|---|---|---|---|']
        for a in acts:
            tid=str(a.get('task_id') or f"ACTION-{a.get('project_id') or 'unknown'}"); pid=str(a.get('project_id') or '').strip(); Q.append(f'| {fmt(a.get("priority"))} | {fmt(a.get("due_date"))} | {link("02_CSS/Actions",tid)} | {link("02_CSS/Projects",pid) if pid else "-"} | {link("02_CSS/Institutions",a.get("institution") or "Unknown Institution")} | {fmt(a.get("task_type"))} | {fmt(a.get("reason")).replace("|","/")} |')
    else: Q += ['> DB-derived fallback. Configure the canonical Sheet snapshot for exact task metadata.']+[f'- {link("02_CSS/Projects",p["project_id"])} — {fmt(p.get("stage"))}' for p in acts]
    note(base/'Actions'/'OPEN_ACTIONS.md',Q)

    active=sum(int(p.get('progress_percent') or 0)<100 for p in projects)
    D=['---','type: css_dashboard',f'generated_at: "{generated}"',f'source: {src}','---','','# CSS Dashboard','',f'- Total projects: **{len(projects)}**',f'- Active projects: **{active}**',f'- Completed projects: **{len(projects)-active}**',f'- Action queue: **{len(acts)}**',f'- Institutions: **{len(by_i)}**',f'- Customers: **{len(by_c)}**','','## Top institutions','']
    for k,v in sorted(by_i.items(),key=lambda x:len(x[1]),reverse=True)[:20]: D.append(f'- {link("02_CSS/Institutions",k)} — {len(v)} projects')
    D += ['','## Services','']+[f'- {link("02_CSS/Services",k)} — {len(v)}' for k,v in sorted(by_s.items(),key=lambda x:len(x[1]),reverse=True)]+['','## Attention','',f'- {link("02_CSS/Actions","OPEN_ACTIONS","Open action queue")}']
    note(vault/'00_HOME'/'CSS_DASHBOARD.md',D)
    note(vault/'00_HOME'/'HOME.md',['# MasterOS','','## CSS','','- [[00_HOME/CSS_DASHBOARD|CSS Dashboard]]','- [[02_CSS/Actions/OPEN_ACTIONS|CSS Action Queue]]','','## Research','','- [[01_RESEARCH/RESEARCH_INDEX|Research Index]]','','## Source of truth','','- CSS current state: `Novogene_All_Emails` canonical Sheet tabs','- CSS timeline/invoices: `css_project_manager.sqlite3`','- Research: `/srv/is-analysis`','- This Vault is a generated knowledge layer; source systems remain authoritative.'])
    con.close()


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--db',default=os.getenv('CSS_DB','/srv/masteros/cache/css_project_manager.sqlite3')); ap.add_argument('--vault',default=os.getenv('MASTEROS_VAULT','/srv/masteros/vault')); ap.add_argument('--sheet-snapshot',default=os.getenv('CSS_SHEET_SNAPSHOT','')); a=ap.parse_args()
    db=Path(a.db)
    if not db.exists(): raise SystemExit(f'CSS database not found: {db}')
    build(db,Path(a.vault),Path(a.sheet_snapshot) if a.sheet_snapshot else None); print('CSS vault generated:',a.vault)
