from pathlib import Path
import sys, json
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix
from app.config import *
from app.dataset import generate, read
from app.simulator import SCENARIOS
from app.model import train, save
from app.pipeline import analyze

DATA_DIR.mkdir(exist_ok=True); ARTIFACT_DIR.mkdir(exist_ok=True)
train_path=DATA_DIR/"train_normal.jsonl"; cal_path=DATA_DIR/"calibration_normal.jsonl"; test_path=DATA_DIR/"test_all.jsonl"
print("[1/4] Generation des donnees synthetiques...")
generate(train_path,["normal"],TRAIN_NORMAL_WINDOWS,SEED)
generate(cal_path,["normal"],CALIBRATION_NORMAL_WINDOWS,SEED+1)
generate(test_path,SCENARIOS,TEST_WINDOWS_PER_SCENARIO,SEED+2)
print("[2/4] Entrainement des deux Isolation Forest...")
bundle=train(read(train_path),read(cal_path),N_ESTIMATORS,FALSE_POSITIVE_QUANTILE,SEED); save(bundle,MODEL_PATH,CALIBRATION_PATH)
print("[3/4] Evaluation...")
rows=[]
for w in read(test_path):
    r=analyze(bundle,w); rows.append({"scenario":w.scenario_truth,"truth_anomaly":w.scenario_truth!="normal","predicted_anomaly":r["is_anomaly"],"behavior_anomaly":r["behavior_anomaly"],"text_novelty":r["text_novelty"],"hard_health_failure":r["hard_health_failure"],"behavior_score":r["behavior_score"],"text_score":r["text_score"],"component":r["diagnosis"]["component"],"action":r["diagnosis"]["action"]})
df=pd.DataFrame(rows); df.to_csv(ARTIFACT_DIR/"evaluation.csv",index=False)
y=df.truth_anomaly.astype(int); pred=df.predicted_anomaly.astype(int)
report={"thresholds":bundle.thresholds,"confusion_matrix":confusion_matrix(y,pred).tolist(),"classification_report":classification_report(y,pred,output_dict=True,zero_division=0),"per_scenario":df.groupby("scenario")["predicted_anomaly"].mean().round(4).to_dict()}
(ARTIFACT_DIR/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print("[4/4] Termine")
print(json.dumps({"confusion_matrix":report["confusion_matrix"],"per_scenario_detection_rate":report["per_scenario"]},indent=2))
