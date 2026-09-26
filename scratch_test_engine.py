import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from navigation.engine import NavigationEngine

try:
    print("Running NavigationEngine('mountain_mission')...")
    engine = NavigationEngine("mountain_mission")
    result = engine.run()
    print(f"Success! Returned {len(result)} records.")
except Exception as e:
    import traceback
    traceback.print_exc()
