from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from common import ensure_dir, json_dump, load_config, write_table

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--pace")
    ap.add_argument("--out-dir")
    a=ap.parse_args()
    cfg=load_config(a.config)
    root=Path(a.out_dir or cfg["paths"]["out_dir"])
    src=Path(a.pace or root/"stage3_pace"/"SUBJECT_ORGAN_AGING_PACE.tsv.gz")
    out=ensure_dir(root/"stage4_discordance")
    p=pd.read_csv(src,sep="\t",compression="infer",low_memory=False)

    wide=p.pivot_table(index="person_id",columns="organ",values="pace_z_within_organ",aggfunc="first")
    nobs=wide.notna().sum(axis=1)
    min_org=int(cfg["clustering"]["min_complete_organs"])
    eligible=wide.loc[nobs>=min_org].copy()
    if eligible.empty:
        raise SystemExit("No participant has enough organ-specific pace estimates.")

    x=SimpleImputer(strategy="median").fit_transform(eligible)
    x=StandardScaler().fit_transform(x)

    kmin=int(cfg["clustering"]["k_min"])
    kmax=min(int(cfg["clustering"]["k_max"]),len(eligible)-1)
    seed=int(cfg["clustering"]["random_state"])
    scan=[]
    best=None
    for k in range(kmin,kmax+1):
        if k<2 or len(eligible)<=k:
            continue
        km=KMeans(n_clusters=k,n_init=50,random_state=seed).fit(x)
        sil=float(silhouette_score(x,km.labels_))
        scan.append({"k":k,"silhouette":sil,"inertia":float(km.inertia_)})
        if best is None or sil>best[0]:
            best=(sil,k,km.labels_)
    if best is None:
        raise SystemExit("Clustering scan failed.")

    labels=best[2]
    cl=eligible.reset_index()[["person_id"]].copy()
    cl["cluster"]=labels.astype(int)+1
    cl["n_organs_observed"]=nobs.loc[eligible.index].to_numpy()

    desc=eligible.copy()
    desc["discordance_sd"]=eligible.std(axis=1,skipna=True)
    desc["discordance_range"]=eligible.max(axis=1,skipna=True)-eligible.min(axis=1,skipna=True)
    desc["mean_pace_z"]=eligible.mean(axis=1,skipna=True)
    desc["max_pace_z"]=eligible.max(axis=1,skipna=True)
    desc["min_pace_z"]=eligible.min(axis=1,skipna=True)
    desc=desc.reset_index()
    cl=cl.merge(desc,on="person_id",how="left")

    organ_cols=list(wide.columns)
    def fastest(row):
        vals=row[organ_cols].dropna()
        return vals.idxmax() if len(vals) else np.nan
    def slowest(row):
        vals=row[organ_cols].dropna()
        return vals.idxmin() if len(vals) else np.nan
    cl["fastest_organ"]=cl.apply(fastest,axis=1)
    cl["slowest_organ"]=cl.apply(slowest,axis=1)

    centroids=(cl.groupby("cluster")[organ_cols+["discordance_sd","mean_pace_z"]].mean().reset_index())
    counts=cl.groupby("cluster").size().rename("n").reset_index()

    write_table(cl,out/"SUBJECT_MULTI_ORGAN_DISCORDANCE_CLUSTER.tsv.gz")
    write_table(pd.DataFrame(scan),out/"CLUSTER_K_SCAN.tsv")
    write_table(centroids,out/"CLUSTER_CENTROIDS.tsv")
    write_table(counts,out/"CLUSTER_COUNTS.tsv")
    info={"subjects":len(cl),"organs":organ_cols,"selected_k":int(best[1]),
          "best_silhouette":float(best[0]),
          "discordance_definition":"Within-person SD/range of organ-specific longitudinal pace z-scores."}
    json_dump(info,out/"STAGE4_SUMMARY.json")
    print(info)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
