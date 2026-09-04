from navigation.engine import NavigationEngine
import math

for mission in ['mountain_mission', 'desert_mission', 'western_ghats_mission', 'flat_plain_mission']:
    with NavigationEngine(mission) as eng:
        recs = eng.run()
    gnss_ok = sum(1 for r in recs if r.gnss_accepted)
    tan_ok  = sum(1 for r in recs if r.tan_valid)
    err = [r.error_3d_m for r in recs if math.isfinite(r.error_3d_m)]
    mean_err = sum(err)/len(err) if err else float('nan')
    drift_last = recs[-1].ins_drift_m
    print(f"{mission}: n={len(recs)} gnss={gnss_ok} tan={tan_ok} mean_err={mean_err:.1f}m drift={drift_last:.1f}m")
