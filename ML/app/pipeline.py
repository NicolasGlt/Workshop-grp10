from .model import score
from .diagnosis import diagnose

def analyze(bundle, window):
    result=score(bundle,window)
    result["diagnosis"]=diagnose(window,result)
    result["window_id"]=window.window_id
    result["scenario_truth"]=window.scenario_truth
    return result
