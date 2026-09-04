import os
from navigation.engine import NavigationEngine

def main():
    missions = [
        'mountain_mission',
        'desert_mission',
        'western_ghats_mission',
        'flat_plain_mission'
    ]
    
    out_dir = os.path.join("data", "exports")
    os.makedirs(out_dir, exist_ok=True)
    
    for mission in missions:
        print(f"Running navigation engine for {mission}...")
        with NavigationEngine(mission) as eng:
            recs = eng.run()
            
        json_path = os.path.join(out_dir, f"{mission}_metrics.json")
        csv_path = os.path.join(out_dir, f"{mission}_records.csv")
        
        NavigationEngine.export_metrics(recs, json_path)
        NavigationEngine.save_results(recs, csv_path)
        print(f"Exported {mission} to {json_path} and {csv_path}")

if __name__ == "__main__":
    main()
