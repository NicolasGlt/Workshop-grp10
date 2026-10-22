import argparse, json
from .config import MODEL_PATH
from .model import load
from .pipeline import analyze
from .simulator import SCENARIOS, generate_window

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("list-scenarios")
    s=sub.add_parser("simulate"); s.add_argument("--scenario",choices=SCENARIOS,required=True); s.add_argument("--count",type=int,default=1)
    sub.add_parser("replay-all")
    a=p.parse_args()
    if a.cmd=="list-scenarios": print("\n".join(SCENARIOS)); return
    bundle=load(MODEL_PATH)
    scenarios=SCENARIOS if a.cmd=="replay-all" else [a.scenario]*a.count
    for i,scenario in enumerate(scenarios):
        r=analyze(bundle,generate_window(scenario,777,i)); print(json.dumps({k:r[k] for k in ["scenario_truth","is_anomaly","behavior_anomaly","text_novelty","hard_health_failure","behavior_score","text_score","diagnosis"]},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
