import json
from pathlib import Path
from .simulator import generate_window
from .schema import Window

def generate(path, scenarios, per_scenario, seed):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8") as f:
        for s_idx,scenario in enumerate(scenarios):
            for i in range(per_scenario):
                f.write(json.dumps(generate_window(scenario,seed+s_idx*101,i).to_dict(),ensure_ascii=False)+"\n")

def read(path):
    with Path(path).open(encoding="utf-8") as f:
        return [Window.from_dict(json.loads(line)) for line in f if line.strip()]
