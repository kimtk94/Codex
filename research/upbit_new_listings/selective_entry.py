#!/usr/bin/env python3
"""Train-only candidate ranking with annual chronological validation.
Research only. Expects feature_asof_rows.csv from the offline feature audit.
"""
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from pathlib import Path
P=Path(__file__).resolve().parent
D=pd.read_csv(P/"feature_asof_rows.csv")
F=["crash_h","entry_h","post_crash_wait_h","pre_entry_drawdown_pct","trailing_hour_turnover_krw","turnover_ratio","trailing_range_pct","initial_1h_turnover_krw"]
for f in ("trailing_hour_turnover_krw","initial_1h_turnover_krw"):
    D[f]=np.log1p(D[f].clip(lower=0))
D["win"]=(D.net_pct>0).astype(int)
def fit(df):
    clf=make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),LogisticRegression(C=.2,max_iter=2000))
    clf.fit(df[F],df.win)
    return clf
tr=D[D.year<=2024];val=D[D.year==2025].copy();hist=D[D.year<=2025];te=D[D.year==2026].copy()
clf=fit(tr);val["score"]=clf.predict_proba(val[F])[:,1]
options=[]
for q in (.5,.7,.8,.9):
    selected=val[val.score>=val.score.quantile(q)]
    if len(selected)>=10:options.append((selected.net_pct.mean(),q,len(selected)))
_,q,_=max(options)
clf=fit(hist)
threshold=float(np.quantile(clf.predict_proba(hist[F])[:,1],q))
te["score"]=clf.predict_proba(te[F])[:,1]
te["buy"]=te.score>=threshold
te.to_csv(P/"selective_entry_2026_scores.csv",index=False)
s=te[te.buy]
print(dict(validation_quantile=q,test_n=len(s),test_mean_net_pct=float(s.net_pct.mean()),test_win_rate=float(s.win.mean()),test_auc=float(roc_auc_score(te.win,te.score))))
