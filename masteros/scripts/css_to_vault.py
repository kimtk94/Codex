#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


INSTITUTION_ALIASES = {
    "ehwa univ.": "Ewha Univ.",
    "ehwa univ,": "Ewha Univ.",
    "ehwa woman university": "Ewha Univ.",
    "ewha univ.": "Ewha Univ.",
    "kyungpook univ.": "Kyungpook National Univ.",
    "kyungpook university": "Kyungpook National Univ.",
    "kyungpook national univ.": "Kyungpook National Univ.",
    "kaist univ.": "KAIST",
    "kaist": "KAIST",
    "aginglab": "AgingLab",
    "aginglab ": "AgingLab",
    "gyeongsang univ.": "Gyeongsang National Univ.",
    "gyeongsang national univ.": "Gyeongsang National Univ.",
    "gnu": "Gyeongsang National Univ.",
    "unist univ.": "UNIST",
    "unist univ": "UNIST",
    "unist": "UNIST",
    "dongguk univ.": "Dongguk Univ.",
    "dongguk univ": "Dongguk Univ.",
    "sookmyung womens university": "Sookmyung Womens Univ.",
    "sookmyung womens univ.": "Sookmyung Womens Univ.",
    "rokit genoics": "ROKIT Genomics",
    "rokit genomics": "ROKIT Genomics",
    "labsmro": "LABSMRO",
    "postec": "POSTECH",
    "postech": "POSTECH",
    "yonsei": "Yonsei Univ.",
    "yonsei univ.": "Yonsei Univ.",
    "dgist univ.": "DGIST",
    "dgist": "DGIST",
}

SPECIES_ANIMAL = (
    "mouse", "mice", "rat", "dog", "canine", "pig", "porcine", "bos taurus",
    "bovine", "bat", "animal", "zebrafish", "rabbit", "monkey", "macaque",
)
MICROBIAL_MARKERS = (
    "mwgs", "m-wgs", "bacteria wgs", "bateria-wgs", "bateria wgs",
    "bacterial wgs", "microbe wgs", "microbial wgs", "fungal wgs",
)


def safe(v, fallback="Unknown"):
    v = re.sub(r'[\\/:*?"<>|]', "_", str(v or fallback).strip())
    return re.sub(r"\s+", " ", v).strip(" .") or fallback


def fmt(v):
    return "-" if v in (None, "") else str(v).replace("\n", " ").strip()


def link(folder, title, label=None):
    return f"[[{folder}/{safe(title)}|{label or title}]]"


def note(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    tmp.replace(path)


def records(matrix):
    if not matrix:
        return []
    h = [str(x).strip() for x in matrix[0]]
    out = []
    for row in matrix[1:]:
        r = {k: (row[i] if i < len(row) else None) for i, k in enumerate(h)}
        if any(v not in (None, "") for v in r.values()):
            out.append(r)
    return out


def snapshot(path):
    if not path or not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    return {
        k: (records(d.get(k, [])) if k != "fetched_at" else d.get(k))
        for k in ("project_dashboard", "action_center", "customer_360", "fetched_at")
    }


def normalize_institution(value, description=""):
    raw = str(value or "").strip()
    key = re.sub(r"\s+", " ", raw).strip().lower()
    if key in INSTITUTION_ALIASES:
        return INSTITUTION_ALIASES[key]

    # Numeric institution fields are occasional parser artifacts. Recover only when
    # the description contains an unambiguous named institution.
    if not raw or re.fullmatch(r"\d+", raw):
        d = str(description or "")
        if re.search(r"Korea Institute of Oriental Medicine", d, flags=re.I):
            return "KIOM"
        m = re.search(r"\bUniversity of ([A-Za-z][A-Za-z .&']{2,60})(?=-|$)", d, flags=re.I)
        if m:
            return "University of " + m.group(1).strip(" .")
        return "Unknown Institution"

    return raw


def classify_service(raw_service, description=""):
    raw = str(raw_service or "Other").strip()
    raw_key = raw.lower()
    d = str(description or "")
    text = f"{raw} {d}".lower().replace("_", " ")
    compact = re.sub(r"[^a-z0-9]+", " ", text)

    # Preserve already-structured categories. Only legacy Other and WGS are
    # aggressively reclassified from project descriptions.
    canonical = {
        "mrna-seq": "mRNA-Seq",
        "amplicon": "Amplicon",
        "proteomics": "Proteomics",
        "metagenome": "Metagenome",
        "metabolomics": "Metabolomics",
        "single-cell rna-seq": "Single-cell RNA-Seq",
        "single-nucleus rna-seq": "Single-nucleus RNA-Seq",
        "nanopore": "Nanopore",
    }
    if raw_key not in {"other", "wgs"} and raw_key in canonical:
        return canonical[raw_key]

    # WGS is split by biological domain. Microbial markers take precedence.
    if raw_key == "wgs" or (raw_key == "other" and "wgs" in compact):
        if any(x in text for x in MICROBIAL_MARKERS) or re.search(r"\bbacter(?:ia|ial)\b", compact):
            return "Microbial WGS"
        if "human" in compact:
            return "Human WGS"
        if "plant" in compact:
            return "Plant WGS"
        if any(x in compact for x in SPECIES_ANIMAL):
            return "Animal WGS"
        if "pcrproduct" not in compact.replace(" ", "") and re.search(r"\bwgs\s*(?:1|2)gb\b", compact):
            return "Microbial WGS"
        return "WGS - Unclassified"

    # RNA / epigenomics / specialty assays frequently sit under legacy "Other".
    if re.search(r"\bmrna[\s-]*seq\b|\bmrnaseq\b|\bmrna\b", compact):
        return "mRNA-Seq"
    if re.search(r"\bsmall[\s-]*rna\b", compact):
        return "small RNA-Seq"
    if re.search(r"\blncrna\b", compact):
        return "lncRNA-Seq"
    if re.search(r"\brip[\s-]*seq\b", compact):
        return "RIP-Seq"
    if re.search(r"\bchip[\s-]*seq\b", compact):
        return "ChIP-Seq"
    if "rrbs" in compact:
        return "RRBS"
    if re.search(r"\bhi[\s-]*c\b", compact):
        return "Hi-C"
    if "epic array" in compact:
        return "EPIC Array"
    if "special shipment" in compact:
        return "Special Shipment"
    if re.search(r"\bpml\b", compact):
        return "PML"
    if re.search(r"\bpmp\b", compact):
        return "PMP"
    if "amplicon" in compact or re.search(r"\b16s", compact):
        return "Amplicon"
    if "metagenome" in compact:
        return "Metagenome"

    return canonical.get(raw_key, raw or "Other")


def customer_guess(desc):
    if not desc:
        return "Unknown Customer"
    parts = [x.strip() for x in desc.split("-") if x.strip()]
    for x in parts:
        if x.lower().startswith("prof."):
            return x
    stop = {
        "wbi", "wobi", "quantification", "other", "mrna-seq", "mrnaseq", "wgs",
        "metagenome", "amplicon", "proteomics",
    }
    for x in reversed(parts):
        if (
            x.lower().replace(" ", "") not in stop
            and not re.search(r"\d", x)
            and re.fullmatch(r"[A-Za-z.]+", x)
            and len(x) >= 5
        ):
            return x
    return "Unknown Customer"


def db_latest(con):
    q = """WITH r AS (
        SELECT *, ROW_NUMBER() OVER(
          PARTITION BY project_id
          ORDER BY datetime(received_at) DESC, processed_at DESC, uid DESC
        ) n
        FROM project_timeline
        WHERE COALESCE(TRIM(project_id),'')<>''
    ) SELECT * FROM r WHERE n=1"""
    return [dict(x) for x in con.execute(q)]


def canonical(snap):
    if not snap:
        return None
    out = []
    for r in snap["project_dashboard"]:
        pid = str(r.get("project_id") or "").strip()
        if not pid or str(r.get("exclude") or "").upper() in {"TRUE", "YES", "1"}:
            continue
        yes = lambda v: str(v or "").strip().lower() in {"yes", "true", "1", "y"}
        try:
            progress = int(float(r.get("progress_percent") or 0))
        except Exception:
            progress = 0
        out.append(
            dict(
                project_id=pid,
                received_at=r.get("latest_email_at"),
                stage=r.get("current_stage") or "Unclassified",
                progress_percent=progress,
                checkpoint=r.get("latest_checkpoint"),
                action_required=int(
                    yes(r.get("latest_action_required")) or yes(r.get("attention"))
                ),
                sample_count=r.get("latest_confirmed_samples") or r.get("received_samples"),
                planned_samples=r.get("planned_samples"),
                institution=r.get("institution") or "Unknown Institution",
                raw_service=r.get("service") or "Other",
                project_description=r.get("project_description"),
                subject=r.get("latest_subject"),
                customer=r.get("customer_name") or "Unknown Customer",
                attention_reason=r.get("attention_reason"),
            )
        )
    return out


def rows(con, sql, args=()):
    return [dict(x) for x in con.execute(sql, args)]


def reset_generated_css(base):
    # 02_CSS is fully generated. Clearing it avoids stale alias/service notes from
    # older normalization versions while leaving user-authored 08_INBOX untouched.
    for name in ("Institutions", "Customers", "Projects", "Services", "Actions"):
        p = base / name
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)


def build(db_path: Path, vault: Path, sheet_snapshot: Path | None = None):
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    snap = snapshot(sheet_snapshot)
    projects = canonical(snap) or db_latest(con)
    generated = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    src = (
        "CSS Project Dashboard + css_project_manager.sqlite3"
        if snap
        else "css_project_manager.sqlite3"
    )

    base = vault / "02_CSS"
    reset_generated_css(base)
    (vault / "00_HOME").mkdir(parents=True, exist_ok=True)

    raw_inst_counts = Counter()
    normalized_inst_counts = Counter()
    observed_institution_aliases = Counter()
    raw_service_counts = Counter()
    normalized_service_counts = Counter()

    by_i, by_c, by_s = defaultdict(list), defaultdict(list), defaultdict(list)
    for p in projects:
        raw_inst = str(p.get("institution") or "Unknown Institution").strip()
        raw_svc = str(p.get("raw_service") or p.get("service") or "Other").strip()
        desc = p.get("project_description") or ""
        raw_inst_counts[raw_inst] += 1
        raw_service_counts[raw_svc] += 1

        p["institution_raw"] = raw_inst
        p["institution"] = normalize_institution(raw_inst, desc)
        observed_institution_aliases[(raw_inst, p["institution"])] += 1
        p["service_raw"] = raw_svc
        p["service"] = classify_service(raw_svc, desc)
        p["customer"] = p.get("customer") or customer_guess(desc)

        normalized_inst_counts[p["institution"]] += 1
        normalized_service_counts[p["service"]] += 1
        by_i[p["institution"]].append(p)
        by_c[p["customer"]].append(p)
        by_s[p["service"]].append(p)

    for p in projects:
        pid = p["project_id"]
        tl = rows(
            con,
            """SELECT received_at,stage,progress_percent,checkpoint,action_required,subject
               FROM project_timeline WHERE project_id=?
               ORDER BY datetime(received_at) DESC, processed_at DESC LIMIT 20""",
            (pid,),
        )
        inv = rows(
            con,
            """SELECT received_at,invoice_number,amount_krw,po_reference
               FROM tax_invoices WHERE project_id=?
               ORDER BY datetime(received_at) DESC""",
            (pid,),
        )
        total = sum(int(x.get("amount_krw") or 0) for x in inv)
        L = [
            "---",
            "type: css_project",
            f"project_id: {pid}",
            f'stage: "{fmt(p.get("stage"))}"',
            f'progress_percent: {int(p.get("progress_percent") or 0)}',
            f'action_required: {str(bool(p.get("action_required"))).lower()}',
            f'generated_at: "{generated}"',
            f"source: {src}",
            "---",
            "",
            f"# {pid}",
            "",
            "## Links",
            "",
            f'- Institution: {link("02_CSS/Institutions", p["institution"])}',
            f'- Customer: {link("02_CSS/Customers", p["customer"])}',
            f'- Service: {link("02_CSS/Services", p["service"])}',
            "",
            "## Normalization",
            "",
            f'- Raw institution: {fmt(p.get("institution_raw"))}',
            f'- Raw service: {fmt(p.get("service_raw"))}',
            "",
            "## Current status",
            "",
            f'- Stage: **{fmt(p.get("stage"))}**',
            f'- Progress: **{int(p.get("progress_percent") or 0)}%**',
            f'- Action required: **{"YES" if p.get("action_required") else "No"}**',
            f'- Planned samples: {fmt(p.get("planned_samples"))}',
            f'- Latest sample count: {fmt(p.get("sample_count"))}',
            f'- Latest email: {fmt(p.get("received_at"))}',
            f'- Description: {fmt(p.get("project_description"))}',
            f'- Invoice total: {total:,} KRW',
            "",
            "## Recent timeline",
            "",
            "| Date | Stage | Progress | Action | Checkpoint | Subject |",
            "|---|---|---:|---|---|---|",
        ]
        for x in tl:
            L.append(
                f'| {fmt(x.get("received_at"))} | {fmt(x.get("stage"))} | '
                f'{int(x.get("progress_percent") or 0)}% | '
                f'{"⚠️" if x.get("action_required") else ""} | '
                f'{fmt(x.get("checkpoint"))} | {fmt(x.get("subject")).replace("|","/")} |'
            )
        if inv:
            L += [
                "",
                "## Invoices",
                "",
                "| Date | Invoice | Amount | PO |",
                "|---|---|---:|---|",
            ]
            for x in inv:
                L.append(
                    f'| {fmt(x.get("received_at"))} | {fmt(x.get("invoice_number"))} | '
                    f'{int(x.get("amount_krw") or 0):,} | {fmt(x.get("po_reference"))} |'
                )
        note(base / "Projects" / f"{safe(pid)}.md", L)

    def index_notes(group, folder, kind, other):
        for name, ps in group.items():
            L = [
                "---",
                f"type: css_{kind}",
                f'generated_at: "{generated}"',
                f"source: {src}",
                "---",
                "",
                f"# {name}",
                "",
                f"- Projects: **{len(ps)}**",
                f'- Active: **{sum(int(x.get("progress_percent") or 0) < 100 for x in ps)}**',
                "",
                "## Projects",
                "",
                f"| Project | {other.title()} | Stage | Progress | Action |",
                "|---|---|---|---:|---|",
            ]
            for p in sorted(ps, key=lambda x: x.get("received_at") or "", reverse=True):
                val = p[other]
                target = (
                    "Customers"
                    if other == "customer"
                    else ("Institutions" if other == "institution" else "Services")
                )
                L.append(
                    f'| {link("02_CSS/Projects", p["project_id"])} | '
                    f'{link("02_CSS/" + target, val)} | {fmt(p.get("stage"))} | '
                    f'{int(p.get("progress_percent") or 0)}% | '
                    f'{"⚠️" if p.get("action_required") else ""} |'
                )
            note(base / folder / f"{safe(name)}.md", L)

    index_notes(by_i, "Institutions", "institution", "customer")
    index_notes(by_c, "Customers", "customer", "institution")
    index_notes(by_s, "Services", "service", "institution")

    acts = []
    if snap:
        closed = {"완료", "해결", "종료", "제외", "closed", "done", "resolved"}
        acts = [
            r
            for r in snap["action_center"]
            if str(r.get("status") or "").strip().lower() not in closed
        ]
        for a in acts:
            tid = str(a.get("task_id") or f"ACTION-{a.get('project_id') or 'unknown'}")
            pid = str(a.get("project_id") or "").strip()
            raw_inst = a.get("institution") or "Unknown Institution"
            inst = normalize_institution(raw_inst, "")
            cust = a.get("customer_name") or "Unknown Customer"
            raw_svc = a.get("service") or "Other"
            svc = classify_service(raw_svc, "")
            L = [
                "---",
                "type: css_action",
                f"task_id: {tid}",
                f'status: "{fmt(a.get("status"))}"',
                f'priority: "{fmt(a.get("priority"))}"',
                f'due_date: "{fmt(a.get("due_date"))}"',
                f'generated_at: "{generated}"',
                "source: CSS Action Center",
                "---",
                "",
                f"# {tid}",
                "",
                f'- Project: {link("02_CSS/Projects",pid) if pid else "-"}',
                f'- Institution: {link("02_CSS/Institutions",inst)}',
                f'- Customer: {link("02_CSS/Customers",cust)}',
                f'- Service: {link("02_CSS/Services",svc)}',
                f'- Owner: {fmt(a.get("owner"))}',
                f'- Task type: {fmt(a.get("task_type"))}',
                "",
                "## Reason",
                "",
                fmt(a.get("reason")),
                "",
                "## Evidence",
                "",
                fmt(a.get("evidence")),
                "",
                "## Recommended action",
                "",
                fmt(a.get("recommended_action")),
                "",
                "## Reply draft — KO",
                "",
                fmt(a.get("reply_draft_ko")),
                "",
                "## Reply draft — EN",
                "",
                fmt(a.get("reply_draft_en")),
                "",
                "## Notes",
                "",
                fmt(a.get("notes")),
                "",
                "## Source",
                "",
                f'- Source link: {fmt(a.get("source_link"))}',
                f'- Evidence UID: {fmt(a.get("evidence_uid"))}',
                f'- Latest email: {fmt(a.get("latest_email_at"))}',
                f'- Updated at: {fmt(a.get("updated_at"))}',
            ]
            note(base / "Actions" / f"{safe(tid)}.md", L)
    else:
        acts = [p for p in projects if p.get("action_required")]

    Q = [
        "---",
        "type: css_action_index",
        f'generated_at: "{generated}"',
        f'source: {"CSS Action Center" if snap else "css_project_manager.sqlite3"}',
        "---",
        "",
        "# CSS Action Queue",
        "",
    ]
    if snap:
        Q += [
            "| Priority | Due | Task | Project | Institution | Type | Reason |",
            "|---|---|---|---|---|---|---|",
        ]
        for a in acts:
            tid = str(a.get("task_id") or f"ACTION-{a.get('project_id') or 'unknown'}")
            pid = str(a.get("project_id") or "").strip()
            inst = normalize_institution(a.get("institution") or "Unknown Institution")
            Q.append(
                f'| {fmt(a.get("priority"))} | {fmt(a.get("due_date"))} | '
                f'{link("02_CSS/Actions",tid)} | '
                f'{link("02_CSS/Projects",pid) if pid else "-"} | '
                f'{link("02_CSS/Institutions",inst)} | {fmt(a.get("task_type"))} | '
                f'{fmt(a.get("reason")).replace("|","/")} |'
            )
    else:
        Q += [
            "> DB-derived fallback. Configure the canonical Sheet snapshot for exact task metadata."
        ] + [
            f'- {link("02_CSS/Projects",p["project_id"])} — {fmt(p.get("stage"))}'
            for p in acts
        ]
    note(base / "Actions" / "OPEN_ACTIONS.md", Q)

    active = sum(int(p.get("progress_percent") or 0) < 100 for p in projects)
    D = [
        "---",
        "type: css_dashboard",
        f'generated_at: "{generated}"',
        f"source: {src}",
        "---",
        "",
        "# CSS Dashboard",
        "",
        f"- Total projects: **{len(projects)}**",
        f"- Active projects: **{active}**",
        f"- Completed projects: **{len(projects)-active}**",
        f"- Action queue: **{len(acts)}**",
        f"- Institutions: **{len(by_i)}**",
        f"- Customers: **{len(by_c)}**",
        "",
        "## Top institutions",
        "",
    ]
    for k, v in sorted(by_i.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
        D.append(f'- {link("02_CSS/Institutions",k)} — {len(v)} projects')
    D += ["", "## Services", ""] + [
        f'- {link("02_CSS/Services",k)} — {len(v)}'
        for k, v in sorted(by_s.items(), key=lambda x: len(x[1]), reverse=True)
    ] + ["", "## Attention", "", f'- {link("02_CSS/Actions","OPEN_ACTIONS","Open action queue")}']
    note(vault / "00_HOME" / "CSS_DASHBOARD.md", D)

    merged_aliases = [
        (raw, norm, n)
        for (raw, norm), n in observed_institution_aliases.items()
        if norm != raw
    ]
    service_changes = []
    for raw, n in raw_service_counts.most_common():
        # distribution of canonical categories for each raw service
        cats = Counter(p["service"] for p in projects if p["service_raw"] == raw)
        service_changes.append((raw, n, cats))

    N = [
        "---",
        "type: normalization_report",
        f'generated_at: "{generated}"',
        "---",
        "",
        "# CSS Normalization Report",
        "",
        f"- Raw institution labels: **{len(raw_inst_counts)}**",
        f"- Canonical institutions: **{len(normalized_inst_counts)}**",
        f"- Raw service labels: **{len(raw_service_counts)}**",
        f"- Canonical services: **{len(normalized_service_counts)}**",
        "",
        "## Institution aliases merged",
        "",
        "| Raw | Canonical | Projects |",
        "|---|---|---:|",
    ]
    for raw, norm, n in sorted(merged_aliases, key=lambda x: (-x[2], x[0].lower())):
        N.append(f"| {raw} | {norm} | {n} |")
    N += ["", "## Service taxonomy", "", "| Raw service | Projects | Canonical distribution |", "|---|---:|---|"]
    for raw, n, cats in service_changes:
        dist = ", ".join(f"{k}: {v}" for k, v in cats.most_common())
        N.append(f"| {raw} | {n} | {dist} |")
    N += ["", "## Canonical service totals", ""]
    for svc, n in normalized_service_counts.most_common():
        N.append(f"- {svc}: **{n}**")
    note(vault / "00_HOME" / "NORMALIZATION_REPORT.md", N)

    note(
        vault / "00_HOME" / "HOME.md",
        [
            "# MasterOS",
            "",
            "## CSS",
            "",
            "- [[00_HOME/CSS_DASHBOARD|CSS Dashboard]]",
            "- [[00_HOME/NORMALIZATION_REPORT|CSS Normalization Report]]",
            "- [[02_CSS/Actions/OPEN_ACTIONS|CSS Action Queue]]",
            "",
            "## Research",
            "",
            "- [[01_RESEARCH/RESEARCH_INDEX|Research Index]]",
            "- [[01_RESEARCH/CKD/CKD_MASTER|CKD Master]]",
            "",
            "## Source of truth",
            "",
            "- CSS current state: `Novogene_All_Emails` canonical Sheet tabs",
            "- CSS timeline/invoices: `css_project_manager.sqlite3`",
            "- Research results: Google Drive `IS_Analysis_V3/results`",
            "- This Vault is a generated knowledge layer; source systems remain authoritative.",
        ],
    )
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.getenv("CSS_DB", "/srv/masteros/cache/css_project_manager.sqlite3"))
    ap.add_argument("--vault", default=os.getenv("MASTEROS_VAULT", "/srv/masteros/vault"))
    ap.add_argument("--sheet-snapshot", default=os.getenv("CSS_SHEET_SNAPSHOT", ""))
    a = ap.parse_args()
    db = Path(a.db)
    if not db.exists():
        raise SystemExit(f"CSS database not found: {db}")
    build(db, Path(a.vault), Path(a.sheet_snapshot) if a.sheet_snapshot else None)
    print("CSS vault generated:", a.vault)