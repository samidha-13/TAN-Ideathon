"""
Navigation Engine — top-level orchestrator.

Reads mission sensor CSV files and runs the full navigation pipeline:

    IMU → INS propagation
        ↓
    EKF predict
        ↓
    FDI checks (radar, GNSS, magnetometer)
        ↓
    TAN matching (if radar accepted + terrain observable)
        ↓
    EKF update (with accepted measurements)
        ↓
    EKF correct INS position
        ↓
    MagNav (independent fallback)
        ↓
    EKF update (MagNav, if available)
        ↓
    Output NavigationRecord per timestep

Ground truth (trajectory.csv) is read ONLY for error evaluation
and is NEVER fed into the navigation estimate.

Usage
-----
    engine = NavigationEngine("mountain_mission")
    results = engine.run()
    engine.save_results(results, "output/mountain_nav.csv")
"""

import os
import csv
import math
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

from navigation.terrain_provider   import SRTMTerrainProvider
from navigation.terrain_observability import (
    sample_elevation_profile_around, compute_observability
)
from navigation.ins                import INSPropagator
from navigation.tan                import TerrainAidedNavigation, TANResult
from navigation.fdi                import FaultDetectionIsolation
from navigation.ekf                import NavigationEKF
from navigation.magnav             import MagNavEstimator

logger = logging.getLogger(__name__)

_REPO_ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DATA_ROOT    = os.path.join(_REPO_ROOT, "data", "missions")
_CONFIG_ROOT  = os.path.join(_REPO_ROOT, "configs", "missions")


# ── output record ─────────────────────────────────────────────────────────────

@dataclass
class NavigationRecord:
    timestamp:          float
    mission_index:      int
    # Navigation estimate (from INS + EKF correction — never from truth)
    estimated_lat:      float
    estimated_lon:      float
    estimated_alt:      float
    nav_mode:           str    # FULL_AID | TAN_ONLY | GNSS_ONLY | MAG_ONLY | INS_ONLY
    # Sensor validity (FDI decisions)
    gnss_accepted:      bool
    radar_accepted:     bool
    mag_accepted:       bool
    # TAN diagnostics
    tan_valid:          bool
    tan_match_score:    float
    tan_residual_m:     float
    terrain_obs:        str    # LOW | MEDIUM | HIGH | N/A
    # MagNav diagnostics
    magnav_available:   bool
    magnav_quality:     str
    # Uncertainty (1-sigma)
    uncertainty_lat_m:  float   # converted to metres
    uncertainty_lon_m:  float
    uncertainty_alt_m:  float
    # FDI fault codes
    fdi_radar:          str
    fdi_gnss:           str
    fdi_mag:            str
    # Error (filled after run, using truth trajectory — only for evaluation)
    truth_lat:          float   = float("nan")
    truth_lon:          float   = float("nan")
    error_lat_m:        float   = float("nan")
    error_lon_m:        float   = float("nan")
    error_3d_m:         float   = float("nan")
    ins_drift_m:        float   = 0.0


# ── engine ────────────────────────────────────────────────────────────────────

class NavigationEngine:
    """
    Full TAN-INS-EKF navigation engine for one mission.

    Parameters
    ----------
    mission_name       : e.g. "mountain_mission"
    fault_scenario     : optional fault scenario name; if None, reads faults.json
                         per-timestep (Samidha's sim output).
    gnss_override      : if set, force GNSS status ("AVAILABLE", "DENIED")
    radar_override     : if set, force radar status ("VALID", "INVALID")
    """

    _M_PER_DEG = 111_320.0

    def __init__(
        self,
        mission_name:  str,
        fault_scenario: Optional[str] = None,
        gnss_override:  Optional[str] = None,
        radar_override: Optional[str] = None,
    ) -> None:
        self.mission_name   = mission_name
        self.fault_scenario = fault_scenario
        self.gnss_override  = gnss_override
        self.radar_override = radar_override

        # Paths
        mission_dir  = os.path.join(_DATA_ROOT, mission_name)
        self._imu_path     = os.path.join(mission_dir, "imu.csv")
        self._gnss_path    = os.path.join(mission_dir, "gnss.csv")
        self._radar_path   = os.path.join(mission_dir, "radar.csv")
        self._mag_path     = os.path.join(mission_dir, "magnetometer.csv")
        self._traj_path    = os.path.join(mission_dir, "trajectory.csv")
        self._faults_path  = os.path.join(mission_dir, "faults.json")
        self._config_path  = os.path.join(_CONFIG_ROOT, f"{mission_name}.json")

        self._config = self._load_json(self._config_path)

        # Terrain
        self._terrain = SRTMTerrainProvider()

        # Components (initialised in run())
        self._ins:    Optional[INSPropagator]         = None
        self._tan:    Optional[TerrainAidedNavigation]= None
        self._fdi:    Optional[FaultDetectionIsolation]= None
        self._ekf:    Optional[NavigationEKF]          = None
        self._magnav: Optional[MagNavEstimator]        = None

    # ── main entry point ──────────────────────────────────────────────────────

    def run(self) -> List[NavigationRecord]:
        """Run the navigation pipeline over the full mission.  Returns records."""

        logger.info("Starting navigation engine: %s", self.mission_name)

        # Load all sensor streams
        imu_rows   = self._load_csv(self._imu_path)
        gnss_rows  = self._load_csv(self._gnss_path)
        radar_rows = self._load_csv(self._radar_path)
        mag_rows   = self._load_csv(self._mag_path)
        traj_rows  = self._load_csv(self._traj_path)  # truth — evaluation only

        if not imu_rows:
            raise RuntimeError(f"No IMU data found at {self._imu_path}")

        # Index truth by mission_index for evaluation
        truth_by_idx = {
            int(float(r["mission_index"])): r for r in traj_rows
        }

        # Initialise from first truth point (this is the ONLY use of truth data:
        # setting the starting position — equivalent to a known launch point)
        first_truth = traj_rows[0] if traj_rows else None
        init_lat  = float(first_truth["latitude"])  if first_truth else 0.0
        init_lon  = float(first_truth["longitude"]) if first_truth else 0.0
        init_alt  = float(first_truth["altitude"])  if first_truth else 1000.0
        init_yaw  = float(first_truth["yaw"])       if first_truth else 0.0

        # Initialise navigation components
        self._ins    = INSPropagator(init_lat, init_lon, init_alt, init_yaw)
        self._tan    = TerrainAidedNavigation(self._terrain, search_radius_m=3000.0, grid_steps=11)
        self._fdi    = FaultDetectionIsolation(persist_steps=3, recovery_steps=5)
        self._ekf    = NavigationEKF(q_pos_deg=1e-7, q_vel=0.02, q_att=1e-4)
        self._magnav = MagNavEstimator(history_len=50)

        records: List[NavigationRecord] = []

        # Align rows by index (all CSVs have same number of rows in Samidha's sim)
        n = min(len(imu_rows), len(gnss_rows), len(radar_rows), len(mag_rows))

        for idx in range(n):
            imu_row   = imu_rows[idx]
            gnss_row  = gnss_rows[idx]
            radar_row = radar_rows[idx]
            mag_row   = mag_rows[idx]

            ts = float(imu_row["timestamp"])
            mi = idx  # mission index = row index

            # ── apply overrides (test scenarios) ──────────────────────────────
            if self.gnss_override:
                gnss_row = dict(gnss_row)
                gnss_row["status"] = self.gnss_override
                if self.gnss_override == "DENIED":
                    gnss_row["latitude"]  = "nan"
                    gnss_row["longitude"] = "nan"
                    gnss_row["altitude"]  = "nan"
                    gnss_row["velocity"]  = "nan"

            if self.radar_override:
                radar_row = dict(radar_row)
                radar_row["status"] = self.radar_override
                if self.radar_override == "INVALID":
                    radar_row["altitude_above_ground_m"] = "nan"

            # ── 1. INS propagation ────────────────────────────────────────────
            dt = 0.1  # 10 Hz fixed
            self._ins.propagate(imu_row, mission_index=mi)
            ins_state = self._ins.state

            # ── 2. EKF predict ────────────────────────────────────────────────
            self._ekf.predict(dt=dt)

            # ── 3. FDI checks ─────────────────────────────────────────────────
            # For radar innovation gate, predict AGL from current INS + SRTM
            terrain_at_ins = self._terrain.get_elevation(ins_state.latitude, ins_state.longitude)
            pred_agl = ins_state.altitude - terrain_at_ins

            gnss_accepted  = self._fdi.check_gnss(
                gnss_row,
                ins_lat=ins_state.latitude,
                ins_lon=ins_state.longitude,
                ins_alt=ins_state.altitude,
            )
            radar_accepted = self._fdi.check_radar(
                radar_row,
                predicted_agl=pred_agl,
                radar_sigma=2.0,
            )
            mag_accepted   = self._fdi.check_magnetometer(mag_row)

            # ── 4. TAN computation (only if radar accepted) ───────────────────
            tan_result: Optional[TANResult] = None
            if radar_accepted:
                agl = float(radar_row.get("altitude_above_ground_m", float("nan")))
                # Observability from terrain around INS position
                elevs, spacing = sample_elevation_profile_around(
                    self._terrain,
                    ins_state.latitude,
                    ins_state.longitude,
                    radius_m=3000.0,
                    n_points=11,
                )
                obs_result = compute_observability(elevs, spacing)

                tan_result = self._tan.compute(
                    ins_lat   = ins_state.latitude,
                    ins_lon   = ins_state.longitude,
                    ins_alt   = ins_state.altitude,
                    radar_agl = agl,
                    obs_result= obs_result,
                )
            else:
                obs_result = None

            # ── 5. MagNav ─────────────────────────────────────────────────────
            magnav_result = self._magnav.update(
                mag_meas  = mag_row,
                ins_lat   = ins_state.latitude,
                ins_lon   = ins_state.longitude,
                mag_valid = mag_accepted,
            )

            # ── 6. EKF updates with accepted measurements ─────────────────────
            gnss_used = False
            if gnss_accepted:
                g_lat = float(gnss_row.get("latitude",  "nan") or "nan")
                g_lon = float(gnss_row.get("longitude", "nan") or "nan")
                g_alt = float(gnss_row.get("altitude",  "nan") or "nan")
                if math.isfinite(g_lat) and math.isfinite(g_lon) and math.isfinite(g_alt):
                    self._ekf.update_gnss(
                        ins_lat=ins_state.latitude, ins_lon=ins_state.longitude, ins_alt=ins_state.altitude,
                        gnss_lat=g_lat, gnss_lon=g_lon, gnss_alt=g_alt,
                    )
                    gnss_used = True

            tan_used = False
            if tan_result is not None and tan_result.valid:
                self._ekf.update_tan(
                    ins_lat=ins_state.latitude, ins_lon=ins_state.longitude,
                    tan_lat=tan_result.estimated_lat, tan_lon=tan_result.estimated_lon,
                    match_score=tan_result.match_score,
                )
                tan_used = True

            mag_used = False
            if magnav_result.available and magnav_result.confidence > 0.2:
                self._ekf.update_magnav(
                    ins_lat=ins_state.latitude, ins_lon=ins_state.longitude,
                    mag_lat=magnav_result.lat, mag_lon=magnav_result.lon,
                    r_m=800.0 / max(magnav_result.confidence, 0.01),
                )
                mag_used = True

            # ── 7. Apply EKF correction to INS ────────────────────────────────
            corr_lat, corr_lon, corr_alt = self._ekf.apply_correction_to_ins(
                ins_state.latitude,
                ins_state.longitude,
                ins_state.altitude,
            )
            self._ins.reset_position(corr_lat, corr_lon, corr_alt)

            # ── 8. Determine navigation mode ──────────────────────────────────
            nav_mode = self._nav_mode(gnss_used, tan_used, mag_used)

            # ── 9. Uncertainty ────────────────────────────────────────────────
            s_lat, s_lon, s_alt = self._ekf.position_uncertainty_1sigma()
            # Convert angular uncertainty to metres
            unc_lat_m = s_lat * self._M_PER_DEG
            unc_lon_m = s_lon * self._M_PER_DEG
            unc_alt_m = s_alt

            # ── 10. Error evaluation (truth only) ─────────────────────────────
            truth = truth_by_idx.get(mi)
            t_lat = t_lon = float("nan")
            e_lat = e_lon = e_3d = float("nan")
            if truth:
                t_lat = float(truth["latitude"])
                t_lon = float(truth["longitude"])
                e_lat = (corr_lat - t_lat) * self._M_PER_DEG
                e_lon = (corr_lon - t_lon) * self._M_PER_DEG * math.cos(math.radians(t_lat))
                e_3d  = math.sqrt(e_lat**2 + e_lon**2)

            # ── 11. Build output record ───────────────────────────────────────
            fdi_status = self._fdi.status_summary()
            rec = NavigationRecord(
                timestamp        = ts,
                mission_index    = mi,
                estimated_lat    = corr_lat,
                estimated_lon    = corr_lon,
                estimated_alt    = corr_alt,
                nav_mode         = nav_mode,
                gnss_accepted    = gnss_accepted,
                radar_accepted   = radar_accepted,
                mag_accepted     = mag_accepted,
                tan_valid        = (tan_result is not None and tan_result.valid),
                tan_match_score  = (tan_result.match_score if tan_result else 0.0),
                tan_residual_m   = (tan_result.residual_m  if tan_result and math.isfinite(tan_result.residual_m) else float("nan")),
                terrain_obs      = (obs_result.level.value if obs_result is not None else "N/A"),
                magnav_available = magnav_result.available,
                magnav_quality   = magnav_result.nav_quality,
                uncertainty_lat_m= unc_lat_m,
                uncertainty_lon_m= unc_lon_m,
                uncertainty_alt_m= unc_alt_m,
                fdi_radar        = fdi_status["radar"],
                fdi_gnss         = fdi_status["gnss"],
                fdi_mag          = fdi_status["magnetometer"],
                truth_lat        = t_lat,
                truth_lon        = t_lon,
                error_lat_m      = e_lat,
                error_lon_m      = e_lon,
                error_3d_m       = e_3d,
                ins_drift_m      = ins_state.pos_drift_m,
            )
            records.append(rec)

        logger.info(
            "Navigation complete: %d steps processed for %s",
            len(records), self.mission_name,
        )
        return records

    # ── output helpers ────────────────────────────────────────────────────────

    @staticmethod
    def save_results(records: List[NavigationRecord], output_path: str) -> None:
        """Save navigation records to CSV."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if not records:
            logger.warning("No records to save.")
            return
        fields = list(records[0].__dataclass_fields__.keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for rec in records:
                row = asdict(rec)
                writer.writerow(row)
        logger.info("Saved %d records → %s", len(records), output_path)

    # ── private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _nav_mode(gnss: bool, tan: bool, mag: bool) -> str:
        if gnss and tan:
            return "FULL_AID"
        if gnss:
            return "GNSS_ONLY"
        if tan and mag:
            return "TAN_MAG"
        if tan:
            return "TAN_ONLY"
        if mag:
            return "MAG_ONLY"
        return "INS_ONLY"

    @staticmethod
    def _load_csv(path: str) -> List[Dict[str, str]]:
        if not os.path.isfile(path):
            logger.warning("CSV not found: %s", path)
            return []
        rows = []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return rows

    @staticmethod
    def _load_json(path: str) -> dict:
        if not os.path.isfile(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def close(self) -> None:
        if self._terrain:
            self._terrain.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
