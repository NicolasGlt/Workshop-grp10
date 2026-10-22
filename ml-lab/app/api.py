from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from .config import MODEL_PATH
from .model import load
from .pipeline import analyze
from .simulator import generate_window, SCENARIOS

state={}
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not MODEL_PATH.exists(): raise RuntimeError("Modele absent. Lancez python scripts/run_all.py")
    state["bundle"]=load(MODEL_PATH)
    yield
    state.clear()

app=FastAPI(title="Resilience ML Local Lab",version="1.0.0",lifespan=lifespan)

@app.get("/health")
def health(): return {"status":"ok","model_loaded":"bundle" in state}

@app.get("/scenarios")
def scenarios(): return {"scenarios":SCENARIOS}

@app.post("/simulate/{scenario}")
def simulate(scenario:str, seed:int=42, index:int=0):
    if scenario not in SCENARIOS: raise HTTPException(404,"Scenario inconnu")
    return analyze(state["bundle"],generate_window(scenario,seed,index))
