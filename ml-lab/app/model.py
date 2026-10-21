import json
from dataclasses import dataclass
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import RobustScaler
from .features import NUMERIC_FEATURES, extract

@dataclass
class Bundle:
    scaler: object
    behavior_model: object
    vectorizer: object
    svd: object
    text_model: object
    thresholds: dict

def train(windows, calibration_windows, n_estimators=500, false_positive_quantile=0.01, seed=42):
    train_ex=[extract(w) for w in windows]; cal_ex=[extract(w) for w in calibration_windows]
    x=np.array([[v[f] for f in NUMERIC_FEATURES] for v,_ in train_ex], dtype=float)
    scaler=RobustScaler().fit(x); xs=scaler.transform(x)
    behavior=IsolationForest(n_estimators=n_estimators, max_samples=min(1024,len(xs)), contamination="auto", n_jobs=-1, random_state=seed).fit(xs)
    vectorizer=TfidfVectorizer(ngram_range=(1,2), min_df=2, max_features=12000, sublinear_tf=True)
    tx=vectorizer.fit_transform([d for _,d in train_ex])
    max_components=max(2,min(96,tx.shape[0]-1,tx.shape[1]-1))
    svd=TruncatedSVD(n_components=max_components, random_state=seed).fit(tx)
    reduced=svd.transform(tx)
    text=IsolationForest(n_estimators=n_estimators, max_samples=min(1024,len(reduced)), contamination="auto", n_jobs=-1, random_state=seed+1).fit(reduced)
    cal_num=scaler.transform(np.array([[v[f] for f in NUMERIC_FEATURES] for v,_ in cal_ex]))
    cal_txt=svd.transform(vectorizer.transform([d for _,d in cal_ex]))
    # sklearn: plus le score est petit, plus l'observation est anormale.
    b_scores=behavior.score_samples(cal_num); t_scores=text.score_samples(cal_txt)
    thresholds={"behavior":float(np.quantile(b_scores,false_positive_quantile)),"text":float(np.quantile(t_scores,false_positive_quantile)),"quantile":false_positive_quantile}
    return Bundle(scaler,behavior,vectorizer,svd,text,thresholds)

def save(bundle,path,calibration_path):
    joblib.dump(bundle,path)
    calibration_path.write_text(json.dumps(bundle.thresholds,indent=2),encoding="utf-8")

def load(path): return joblib.load(path)

def score(bundle, window):
    values,document=extract(window)
    x=bundle.scaler.transform([[values[f] for f in NUMERIC_FEATURES]])
    tx=bundle.svd.transform(bundle.vectorizer.transform([document]))
    bs=float(bundle.behavior_model.score_samples(x)[0]); ts=float(bundle.text_model.score_samples(tx)[0])
    ba=bs < bundle.thresholds["behavior"]; ta=ts < bundle.thresholds["text"]
    hard_health=values["min_health"] < 0.5
    return {"is_anomaly":bool(ba or ta or hard_health),"behavior_anomaly":bool(ba),"text_novelty":bool(ta),"hard_health_failure":bool(hard_health),"behavior_score":bs,"text_score":ts,"features":values}
