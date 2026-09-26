import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from dataclasses import asdict
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from navigation.engine import NavigationEngine

app = FastAPI(title="TAN Navigation Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MISSIONS = {
    "mountain_mission": "Mountain",
    "desert_mission": "Desert",
    "western_ghats_mission": "Plateau",
    "flat_plain_mission": "Flat Plain"
}

# Cache to avoid re-running the same mission simulation
mission_cache = {}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "TAN Navigation Backend"}

@app.get("/api/missions")
def get_missions():
    return [{"id": k, "name": v} for k, v in MISSIONS.items()]

@app.get("/api/navigation/{mission_id}/state")
def get_navigation_state(mission_id: str):
    if mission_id not in MISSIONS:
        raise HTTPException(status_code=404, detail="Mission not found")
        
    if mission_id in mission_cache:
        return mission_cache[mission_id]
        
    try:
        engine = NavigationEngine(mission_id)
        records = engine.run()
        
        def clean_nan(obj):
            if isinstance(obj, float):
                return None if math.isnan(obj) or math.isinf(obj) else obj
            if isinstance(obj, dict):
                return {k: clean_nan(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [clean_nan(v) for v in obj]
            return obj
            
        # Convert dataclasses to dicts and clean NaNs
        results = clean_nan([asdict(rec) for rec in records])
        mission_cache[mission_id] = results
        return results
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
