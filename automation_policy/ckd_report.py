"""Evidence-only CKD cross-stage report; never re-labels inherited results as new MR."""
import csv,json,math
from pathlib import Path
def rows(folder,name):
    with (folder/name).open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f,delimiter="\t"))
def produce(folder,out):
    a=rows(folder,"STAGE2B_COLOC_DEFAULT.tsv")
    b=rows(folder,"STAGE2C_SUSIE_DEFAULT.tsv")
    c=rows(folder,"STAGE3A_KIDNEY_EVIDENCE.tsv")
    d=rows(folder,"STAGE3B_INTEGRATED_EVIDENCE.tsv")
    if not a or any(len(x)!=len(a) for x in (b,c,d)):
        raise ValueError("stage_row_count_discrepancy")
    genes=[r["gene_symbol"] for r in a]
    if len(set(genes))!=len(genes) or any(set(genes)!={r["gene_symbol"] for r in tbl} for tbl in (b,c,d)):
        raise ValueError("stage_gene_mismatch")
    bmap={r["gene_symbol"]:r for r in b}
    cmap={r["gene_symbol"]:r for r in c}
    dmap={r["gene_symbol"]:r for r in d}
    common=set(c[0]).intersection(d[0])-{"gene_symbol"}
    for gene in genes:
        if abs(float(bmap[gene]["stage2b_ABF_PP.H4"])-float(next(r for r in a if r["gene_symbol"]==gene)["PP.H4"]))>1e-8:
            raise ValueError("abf_mismatch")
        if any(cmap[gene][f]!=dmap[gene][f] for f in common): raise ValueError("kidney_evidence_mismatch")
    summary=[]
    for row in a:
        g=row["gene_symbol"]
        v=bmap[g]["max_PP.H4"]
        summary.append({"gene":g,"abf_pph4":float(row["PP.H4"]),"susie_max_pph4":None if v in ("","NA") else float(v)})
    summary.sort(key=lambda x:x["abf_pph4"],reverse=True)
    out.mkdir(parents=True,exist_ok=True)
    result={"status":"CROSS_STAGE_QC_PASS","genes":len(genes),"scientific_recomputation":False,"results":summary}
    (out/"ckd-summary.json").write_text(json.dumps(result,indent=2)+"\n")
    lines=["# CKD Stage 2B–3B recovered-results QC","",
           "**Original validated research outputs; no new MR, coloc or SuSiE run.**","",
           "| Gene | ABF PP.H4 | SuSiE max PP.H4 |","|---|---:|---:|"]
    lines += [f"| {r['gene']} | {r['abf_pph4']:.4f} | {r['susie_max_pph4']:.4f} |" if r["susie_max_pph4"] is not None else f"| {r['gene']} | {r['abf_pph4']:.4f} | unresolved |" for r in summary]
    lines+=["","Cross-stage gene identity, ABF agreement and Stage3 shared fields: PASS.","",
            "Controlled KoGES validation and new scientific analyses: NOT RUN."]
    (out/"ckd-summary.md").write_text("\n".join(lines)+"\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,5))
    y=list(range(len(summary)))
    ax.scatter([r["abf_pph4"] for r in summary],y,label="ABF coloc PP.H4")
    ax.scatter([float("nan") if r["susie_max_pph4"] is None else r["susie_max_pph4"] for r in summary],y,label="SuSiE max PP.H4",marker="s")
    ax.set_yticks(y,[r["gene"] for r in summary]);ax.invert_yaxis()
    ax.set_xlim(-.02,1.02);ax.set_xlabel("Posterior probability")
    ax.set_title("CKD recovered result comparison (not a new analysis)")
    ax.grid(axis="x",alpha=.3);ax.legend();fig.tight_layout()
    fig.savefig(out/"ckd-abf-susie.png",dpi=160);plt.close(fig)
    return result
if __name__=="__main__":
    print(json.dumps(produce(Path("artifacts/ckd-drive/inputs"),Path("artifacts/ckd-drive/reports"))))
