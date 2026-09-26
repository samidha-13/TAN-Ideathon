# TAN Simulation Backend

This project implements a deterministic aircraft sensor simulation layer for the TAN (Terrain-Aided Navigation) project. It serves as the foundational data generator for the subsequent INS → TAN → FDI → EKF navigation pipeline.

## Project Purpose
The primary purpose is to generate a deterministic sequence of simulated aircraft states (`MissionState`) serving as a single source of truth. Simulated IMU, GNSS, Radar, and Magnetometer models consume this source of truth to produce synthetic measurements, including configurable noise, bias, and dynamic fault scenarios.

## Repository Structure
- `configs/missions/`: JSON configuration files defining the boundary, waypoints, velocity, altitude, and seed for 4 fixed geographical missions.
- `data/missions/`: Generated output data (CSV) and fault logs (JSON).
- `simulator/`: Core generation models including Trajectory, IMU, GNSS, Radar Altimeter, Magnetometer, and Fault Injection.
- `synchronization/`: Mission clock management and the `MissionState` dataclass definition.
- `tests/unit/`: Comprehensive test suite verifying boundaries, determinism, interface adherence, and fault logic.
- `scripts/`: Scripts to instantiate the simulator and output all CSV datasets.

## Fixed Geographic Areas
Four strictly bounded regions have been defined:
1. **Mountain (Uttarakhand)**: 30.0–30.3° N, 78.0–78.4° E
2. **Desert (Rajasthan)**: 26.5–27.0° N, 70.5–71.0° E
3. **Plateau / Western Ghats (Goa)**: 15.0–15.5° N, 73.7–74.2° E
4. **Flat Plain (Uttar Pradesh)**: 25.0–25.5° N, 81.5–82.0° E

## Architecture Highlights
- **Single Source of Truth**: All sensor models are driven directly by a synchronized `MissionState` object; they do not generate random disconnected positions.
- **Terrain & Magnetic Mapping**: The radar altimeter interface (`TerrainElevationProvider`) is currently mocked, but designed to consume SRTM 1 Arc-Second Global (~30 m) elevation data in downstream modules. The Magnetometer relies on a similarly designed `MagneticReferenceProvider` interface.
- **Fault Injection**: Dynamic simulation of GNSS denial/degradation, radar faults, magnetometer faults, and multi-sensor failures.

## Data Formats
Generated data is saved to `data/missions/<mission_name>/`.
Output formats include CSVs containing timestamps, geographic coordinates, and respective sensor measurements (e.g. `ax, ay, az, roll_rate...` for IMU).
Timestamps are strictly synchronized across all sensors via the `MissionClock`.

## Intentionally NOT Implemented
The following features are out of scope for this foundational layer and have been explicitly avoided:
- Terrain-Aided Navigation (TAN) or Terrain Matching
- Digital Elevation Model (DEM) logic (no fake SRTM data provided)
- Extended Kalman Filter (EKF) and Fault Detection/Isolation (FDI)
- Magnetic Anomaly Navigation (MagNav)
- Machine Learning (ML)
- Google Earth integrations

## How to Run a Mission
Generate simulated datasets for all missions using the provided script:
```bash
python scripts/generate_sensor_data.py
```
To run a specific mission:
```bash
python scripts/generate_sensor_data.py --mission mountain_mission
```

## How to Run Tests
The repository includes a comprehensive unit test suite:
```bash
python -m unittest discover tests/unit
```
