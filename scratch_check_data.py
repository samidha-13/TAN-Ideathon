import sys
import os
import pandas as pd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from navigation.engine import load_mission_data

try:
    print("Loading mountain_mission data...")
    truth, sensors = load_mission_data("mountain_mission")
    print("GNSS sample:")
    print(sensors["gnss"][0])
    print("Radar sample:")
    print(sensors["radar"][0])
    print("Magnetometer sample:")
    print(sensors["magnetometer"][0])
except Exception as e:
    import traceback
    traceback.print_exc()
