import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.generate_sensor_data import run_mission

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a single mission")
    parser.add_argument('mission_name', type=str, help="Mission name (e.g. mountain_mission)")
    args = parser.parse_args()
    
    run_mission(args.mission_name)
