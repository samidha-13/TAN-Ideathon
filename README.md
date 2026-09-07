# TAN Navigation System

## Adaptive & Fault-Tolerant Terrain-Aided Navigation for GNSS-Denied Flight

A prototype navigation system designed to maintain aircraft navigation when Global Navigation Satellite System (GNSS) signals are denied or degraded.

The system combines Inertial Navigation System (INS), Terrain-Aided Navigation (TAN), Fault Detection and Isolation (FDI), Extended Kalman Filter (EKF), and Magnetic Anomaly Navigation (MagNav).

## What We Implemented

- **Inertial Navigation System (INS)** – continuous aircraft state propagation using Inertial Measurement Unit (IMU) data.
- **Terrain-Aided Navigation (TAN)** – uses Radar Altimeter measurements and Digital Elevation Model (DEM) terrain data for terrain matching.
- **Terrain Observability** – evaluates how informative the surrounding terrain is for TAN.
- **Fault Detection and Isolation (FDI)** – detects abnormal sensor behaviour and isolates faulty measurements.
- **Extended Kalman Filter (EKF)** – fuses INS with valid navigation measurements and maintains navigation uncertainty.
- **Magnetic Anomaly Navigation (MagNav)** – provides an additional navigation aid using magnetic-field information.
- **Fault Injection** – simulates GNSS denial and sensor-fault scenarios.
- **Deterministic Mission Replay** – allows repeatable demonstration of the navigation workflow.

## System Architecture

Use this architecture:

IMU → INS ─────────────────┐
                           │
Radar Altimeter → TAN ─────┤
                           ├→ FDI → EKF → Navigation State
Magnetometer → MagNav ─────┤
                           │
GNSS ──────────────────────┘

TAN uses SRTM Digital Elevation Model (DEM) terrain data for terrain matching.

FDI determines which sensor measurements are valid before they are used by the fusion layer.

EKF produces the final estimated navigation state.

## Terrain-Aided Navigation (TAN)

TAN uses the radar altimeter's Above Ground Level (AGL) measurement together with aircraft altitude to estimate terrain elevation.

The estimated terrain information is compared with SRTM terrain data to determine the best terrain match.

Terrain observability is also evaluated because mountainous terrain generally provides more distinctive terrain information than flat terrain.

## Data Sources

- SRTM 1 Arc-Second Global (~30 m) Digital Elevation Model
- Deterministic aircraft trajectory data
- Simulated IMU data
- Simulated GNSS data
- Simulated radar-altimeter data
- Simulated magnetometer data
- Magnetic reference data where available in the implementation

Mission environments:

- Mountain — Uttarakhand
- Desert — Rajasthan
- Western Ghats — Goa
- Flat Plain — Uttar Pradesh

## Technology Stack

### Backend / Navigation

- Python
- NumPy
- Rasterio
- Python Unit Testing
- INS
- TAN
- Terrain Observability
- FDI
- EKF
- MagNav

### Frontend

- React
- TypeScript
- Vite
- Three.js
- CesiumJS
- Cesium ion

### Visualization

- Three.js → Forward Pilot View / 3D terrain
- CesiumJS → Tactical Navigation Map / 3D geographic terrain

## Project Structure

```text
configs/
data/
frontend/
navigation/
├── ekf.py
├── engine.py
├── fdi.py
├── ins.py
├── magnav.py
├── tan.py
├── terrain_observability.py
└── terrain_provider.py
scripts/
simulator/
├── faults.py
├── gnss_model.py
├── imu_model.py
├── magnetometer.py
├── radar_altimeter.py
└── trajectory.py
synchronization/
terrain/
tests/
```

## How to Run

### Backend / Simulation

From the repository root:

```bash
python -m venv .venv
# Activate the virtual environment
# Windows: .venv\Scripts\activate
# Unix/MacOS: source .venv/bin/activate

pip install -r requirements.txt

# Generate simulated datasets
python scripts/generate_sensor_data.py

# Run test suite
python -m unittest discover tests/unit
```

### Frontend Visualization

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```
