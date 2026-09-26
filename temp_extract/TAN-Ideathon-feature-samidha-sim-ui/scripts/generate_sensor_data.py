import os
import sys
import json
import csv
import argparse
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from simulator.trajectory import TrajectoryGenerator
from simulator.imu_model import IMUModel
from simulator.gnss_model import GNSSModel
from simulator.radar_altimeter import RadarAltimeter, MockTerrainProvider
from simulator.magnetometer import Magnetometer, MockMagneticProvider
from simulator.faults import FaultManager

def load_config(mission_name: str) -> Dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'missions', f'{mission_name}.json')
    with open(config_path, 'r') as f:
        return json.load(f)

def save_csv(data: List[Dict[str, Any]], output_path: str):
    if not data:
        return
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    keys = data[0].keys()
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

def run_mission(mission_name: str, inject_faults: bool = True):
    config = load_config(mission_name)
    
    trajectory_gen = TrajectoryGenerator(config)
    fault_manager = FaultManager()
    
    imu = IMUModel(config)
    gnss = GNSSModel(config)
    radar = RadarAltimeter(config, MockTerrainProvider())
    mag = Magnetometer(config, MockMagneticProvider())
    
    print(f"Generating trajectory for {mission_name}...")
    states = trajectory_gen.generate()
    
    imu_data = []
    gnss_data = []
    radar_data = []
    mag_data = []
    faults_log = []
    
    print("Generating sensor data...")
    for state in states:
        if inject_faults:
            if state.timestamp > 10 and state.timestamp < 20:
                fault_manager.apply_scenario("GNSS denied")
            elif state.timestamp > 30 and state.timestamp < 40:
                fault_manager.apply_scenario("radar fault")
            elif state.timestamp > 50 and state.timestamp < 60:
                fault_manager.apply_scenario("magnetometer fault")
            elif state.timestamp > 70 and state.timestamp < 80:
                fault_manager.apply_scenario("combined sensor failure")
            else:
                fault_manager.apply_scenario("baseline")
                
        faults_log.append({
            'timestamp': state.timestamp,
            'gnss_status': fault_manager.gnss_status.name,
            'radar_status': fault_manager.radar_status.name,
            'magnetometer_status': fault_manager.magnetometer_status.name
        })
            
        imu_data.append(imu.generate_measurement(state))
        gnss_data.append(gnss.generate_measurement(state, fault_manager))
        radar_data.append(radar.generate_measurement(state, fault_manager))
        mag_data.append(mag.generate_measurement(state, fault_manager))
        
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'missions', mission_name)
    
    state_dicts = []
    for s in states:
        d = s.__dict__.copy()
        state_dicts.append(d)
        
    save_csv(state_dicts, os.path.join(output_dir, 'trajectory.csv'))
    save_csv(imu_data, os.path.join(output_dir, 'imu.csv'))
    save_csv(gnss_data, os.path.join(output_dir, 'gnss.csv'))
    save_csv(radar_data, os.path.join(output_dir, 'radar.csv'))
    save_csv(mag_data, os.path.join(output_dir, 'magnetometer.csv'))
    
    import json
    with open(os.path.join(output_dir, 'faults.json'), 'w') as f:
        json.dump(faults_log, f, indent=2)
    
    print(f"Data saved to {output_dir}")

def main():
    parser = argparse.ArgumentParser(description="Generate Sensor Data")
    parser.add_argument('--mission', type=str, default='all', help="Mission name or 'all'")
    args = parser.parse_args()
    
    if args.mission == 'all':
        missions = ['mountain_mission', 'desert_mission', 'western_ghats_mission', 'flat_plain_mission']
        for m in missions:
            run_mission(m)
    else:
        run_mission(args.mission)

if __name__ == "__main__":
    main()
