import sys
import os
import math
import time
from dataclasses import asdict
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from navigation.engine import NavigationEngine

try:
    print("Running NavigationEngine('mountain_mission')...")
    t0 = time.time()
    engine = NavigationEngine("mountain_mission")
    records = engine.run()
    t1 = time.time()
    print(f"engine.run() took {t1 - t0:.2f} seconds.")
    print(f"Returned {len(records)} records.")
    
    def clean_nan(obj):
        if isinstance(obj, float):
            return None if math.isnan(obj) or math.isinf(obj) else obj
        if isinstance(obj, dict):
            return {k: clean_nan(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [clean_nan(v) for v in obj]
        return obj
        
    print("Testing clean_nan and asdict...")
    t2 = time.time()
    results = clean_nan([asdict(rec) for rec in records])
    t3 = time.time()
    print(f"clean_nan took {t3 - t2:.2f} seconds.")
    
    import json
    t4 = time.time()
    json.dumps(results)
    t5 = time.time()
    print(f"json serialization took {t5 - t4:.2f} seconds.")
    
except Exception as e:
    import traceback
    traceback.print_exc()
