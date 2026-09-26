import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from navigation.engine import NavigationEngine

try:
    engine = NavigationEngine("mountain_mission")
    gnss_rows = engine._load_csv(engine._gnss_path)
    radar_rows = engine._load_csv(engine._radar_path)
    mag_rows = engine._load_csv(engine._mag_path)

    print("GNSS sample (first 3):")
    for r in gnss_rows[:3]:
        print(f"  status={r.get('status')}")

    print("Radar sample (first 3):")
    for r in radar_rows[:3]:
        print(f"  altitude_above_ground_m={r.get('altitude_above_ground_m')}")

    print("Mag sample (first 3):")
    for r in mag_rows[:3]:
        print(f"  mag_x={r.get('mag_x')}, mag_y={r.get('mag_y')}, mag_z={r.get('mag_z')}")

except Exception as e:
    import traceback
    traceback.print_exc()
