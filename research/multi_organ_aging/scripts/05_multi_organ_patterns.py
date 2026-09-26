#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

INFILE = Path("/srv/is-analysis/results/multi_organ_aging/stage3_pace/ORGAN_AGING_PACE_WIDE.tsv.gz")
OUT = Path("/srv/is-analysis/results/multi_organ_aging/stage4_patterns")
SEED = 20260927

OUT.mkdir(parents=True, exist_ok=True)
df = pd.read_csv(INFILE, sep="\t")
features = [c for c in df.columns if c.endswith("_accel_slope")]
if len(features) < 2:
    raise RuntimeError("Need at least two organ-specific pace variables.")

X0 = df[features].replace([np.inf, -np.inf], np.nan)
imputer = SimpleImputer(strategy="median")
scaler = StandardScaler()
X = scaler.fit_transform(imputer.fit_transform(X0))

zcols = [c.replace("_accel_slope", "_pace_z") for c in features]
for i, c in enumerate(zcols):
    df[c] = X[:, i]

df["mean_aging_z"] = np.nanmean(X, axis=1)
df["max_aging_z"] = np.nanmax(X, axis=1)
df["min_aging_z"] = np.nanmin(X, axis=1)
df["organ_discordance_z"] = np.nanstd(X, axis=1)
df["accelerated_organ_count"] = (X > 1.0).sum(axis=1)
df["decelerated_organ_count"] = (X < -1.0).sum(axis=1)

ncomp = min(2, X.shape[1])
pcs = PCA(n_components=ncomp, random_state=SEED).fit_transform(X)
df["aging_pc1"] = pcs[:, 0]
df["aging_pc2"] = pcs[:, 1] if ncomp > 1 else np.nan

best = None
scores = {}
n = len(df)
for k in range(2, min(6, n - 1)):
    if n < k * 5:
        continue
    km = KMeans(n_clusters=k, random_state=SEED, n_init=50)
    labels = km.fit_predict(X)
    if len(set(labels)) < 2:
        continue
    score = silhouette_score(X, labels)
    scores[str(k)] = float(score)
    if best is None or score > best[0]:
        best = (score, k, labels)

if best is not None:
    df["aging_cluster"] = best[2].astype(int)
    best_k = int(best[1])
else:
    df["aging_cluster"] = -1
    best_k = None

df.to_csv(OUT / "MULTI_ORGAN_AGING_PATTERNS.tsv.gz", sep="\t", index=False, compression="gzip")
qc = {
    "subjects": int(len(df)),
    "organ_features": features,
    "selected_k": best_k,
    "silhouette_scores": scores,
}
(OUT / "STAGE4_PATTERN_QC.json").write_text(json.dumps(qc, indent=2))
print(json.dumps(qc, indent=2))
