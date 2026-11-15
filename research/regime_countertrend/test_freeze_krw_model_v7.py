import json
import unittest
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from research.regime_countertrend.correlated_factor_model import FEATURES
from research.regime_countertrend.peer_macro_v4 import MACRO_COLS
from research.regime_countertrend.krw_detail_regime_v5 import FX_FEATURES
from research.regime_countertrend.freeze_krw_model_v7 import (
    MODEL_NAME,FIRST_PROSPECTIVE,LAST_TRAIN_SESSION,
    _package_scale_pca,latent_numpy,score_frozen_json,_score_matrix,
    validate_frozen_integrity,
)

class KRWProspectiveFreezeV7Tests(unittest.TestCase):
    def valid_fixture(self):
        rng=np.random.default_rng(9876)
        raw=rng.normal(0,1,size=(225,len(FEATURES)))
        etf=rng.normal(0,1,size=(225,len(MACRO_COLS)))
        fx=rng.normal(0,1,size=(225,len(FX_FEATURES)))
        f=pd.DataFrame(raw,columns=FEATURES)
        for j,col in enumerate(MACRO_COLS):f[col]=etf[:,j]
        for j,col in enumerate(FX_FEATURES):f[col]=fx[:,j]
        f["date"]=["2026-11-16"]*len(f)
        f["event"]=["UP_DIP","DOWN_RALLY","SIDE_DIP"]*(len(f)//3)
        f["qqq_atr_pct"]=np.abs(raw[:,0])
        def block(data,columns,n,variance=False):
            sc=StandardScaler().fit(data)
            pca=PCA(n_components=n,svd_solver="full").fit(np.clip(sc.transform(data),-8,8))
            return _package_scale_pca(columns,sc,pca,variance),sc,pca
        tech,st,pt=block(raw,FEATURES,8,True)
        macro,sm,pm=block(etf,MACRO_COLS,3,False)
        currency,sf,pf=block(fx,FX_FEATURES,2,False)
        n=8+2+3+2+1
        coef=rng.normal(0,.1,size=n)
        model={"model":MODEL_NAME,
               "technical_blocks":[tech],"macro_etf":macro,"krw_fx":currency,
               "classifier_coef":coef.tolist(),"classifier_intercept":.05,
               "raw_technical_features":list(FEATURES),
               "high_vol_cutoff":.8,
               "training_last_session":LAST_TRAIN_SESSION,
               "max_training_exit_date":LAST_TRAIN_SESSION,
               "prospective_starts":FIRST_PROSPECTIVE,
               "no_retraining":True,"promotion_allowed":False}
        return f,model,(st,pt,sm,pm,sf,pf)

    def test_all_20_columns_and_model_provenance_preserved(self):
        f,model,_=self.valid_fixture()
        self.assertTrue(validate_frozen_integrity(model))
        self.assertEqual(len(model["raw_technical_features"]),20)
        self.assertEqual(len(model["macro_etf"]["columns"]),10)
        self.assertEqual(len(model["krw_fx"]["columns"]),4)
        self.assertEqual(len(score_frozen_json(f.iloc[:4],model)),4)

    def test_portable_numpy_probability_matches_sklearn_matrix(self):
        f,model,models=self.valid_fixture()
        st,pt,sm,pm,sf,pf=models
        X=f.iloc[:12]
        tech=(pt.transform(np.clip(st.transform(X[FEATURES]),-8,8))/
              np.sqrt(np.maximum(pt.explained_variance_,1e-12)))
        context=np.column_stack([
            (X.event=="DOWN_RALLY").astype(float).to_numpy(),
            (X.event=="SIDE_DIP").astype(float).to_numpy()])
        macro=pm.transform(np.clip(sm.transform(X[list(MACRO_COLS)]),-8,8))
        currency=pf.transform(np.clip(sf.transform(X[list(FX_FEATURES)]),-8,8))
        high=(X.qqq_atr_pct>.8).astype(float).to_numpy()[:,None]
        matrix=np.column_stack([tech,context,macro,currency,high])
        logit=matrix@np.asarray(model["classifier_coef"])+.05
        expected=1/(1+np.exp(-logit))
        actual=score_frozen_json(X,model)
        np.testing.assert_allclose(actual,expected,rtol=1e-12,atol=1e-12)
        np.testing.assert_allclose(
            _score_matrix(X,model),expected,rtol=1e-12,atol=1e-12)

    def test_cannot_label_backtested_events_as_prospective(self):
        f,model,_=self.valid_fixture()
        f.loc[0,"date"]="2026-11-13"
        with self.assertRaisesRegex(ValueError,"before frozen model launch"):
            score_frozen_json(f,model)

    def test_strict_hold_on_unknown_pretrained_origin_or_future_training_label(self):
        f,model,_=self.valid_fixture()
        model["max_training_exit_date"]="2026-11-12"
        with self.assertRaisesRegex(ValueError,"lookahead"):
            validate_frozen_integrity(model)
        model["max_training_exit_date"]=LAST_TRAIN_SESSION
        model["promotion_allowed"]=True
        with self.assertRaises(ValueError):
            validate_frozen_integrity(model)
        with self.assertRaises(ValueError):
            score_frozen_json(f,model)

    def test_missing_fx_column_cannot_silently_fill(self):
        f,model,_=self.valid_fixture()
        with self.assertRaises(ValueError):
            score_frozen_json(f.drop(columns=[FX_FEATURES[0]]),model)

    def test_serialized_json_roundtrip_keeps_predictions(self):
        f,model,_=self.valid_fixture()
        encoded=json.dumps(model,sort_keys=True,separators=(",",":"))
        decoded=json.loads(encoded)
        np.testing.assert_allclose(score_frozen_json(f.head(8),model),
                                  score_frozen_json(f.head(8),decoded),atol=0,rtol=0)

if __name__=="__main__":unittest.main()
