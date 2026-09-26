# LSTM Integration Guide (KnowBuild Branch)

This document contains everything required for the backend/navigation team (Khushi) to integrate the final Machine Learning FDI Watchdog into the navigation loop.

## 1. Artifact Paths

The finalized model and its corresponding standard scaler are saved here:
- **Model:** `ml_fdi/models/lstm_optimized_final.keras`
- **Scaler:** `ml_fdi/models/lstm_sequence_scaler.pkl`

## 2. Input Specification

The ML model expects a strictly ordered sequence of raw sensor measurement residuals. It operates at **10 Hz**.

- **Expected Shape:** `(50, 9)`
- **Time Window:** 50 consecutive timesteps (representing the last 5.0 seconds of flight).
- **Features per Timestep (Strict Order):**
  1. `gnss_residual_lat` (GNSS Latitude residual in meters)
  2. `gnss_residual_lon` (GNSS Longitude residual in meters)
  3. `gnss_residual_alt` (GNSS Altitude residual in meters)
  4. `gnss_residual_3d_m` (GNSS 3D magnitude residual in meters)
  5. `delta_gnss_residual_3d_m` (Instantaneous step-change from previous sample)
  6. `radar_residual_agl` (Radar Altimeter residual in meters)
  7. `delta_radar_residual_agl` (Instantaneous step-change from previous sample)
  8. `mag_total_field` (Magnetometer magnitude residual in nT or normalized)
  9. `delta_mag_total_field` (Instantaneous step-change from previous sample)

*Note: All values must be the pre-FDI physical differences between the sensor measurement and the EKF's predicted prior state.*

## 3. Output Specification (Class Mapping)

The model will predict the current state of the sensors mapped to one of 5 integers:
- `0` = HEALTHY
- `1` = GNSS_FAULT
- `2` = RADAR_FAULT
- `3` = MAGNETOMETER_FAULT
- `4` = COMBINED_FAULT

## 4. Inference Module

We have provided a clean, dependency-free wrapper module located at:
`ml_fdi/inference.py`

### Python Example:

```python
import numpy as np
from ml_fdi.inference import FDIWatchdog

# 1. Initialize the watchdog once (it loads the model and scaler automatically)
watchdog = FDIWatchdog()

# 2. Collect 50 samples of the 9 features in real-time
# (Example mock array of shape 50x9)
raw_sensor_buffer = np.zeros((50, 9)) 

# 3. Predict!
result = watchdog.predict(raw_sensor_buffer)

print(result['predicted_class']) # e.g. "HEALTHY"
print(result['confidence'])      # e.g. 0.95
print(result['probabilities'])   # e.g. {"HEALTHY": 0.95, "GNSS_FAULT": 0.01, ...}
```

## 5. Smoke Test

To verify the integration locally before pushing, run the provided smoke test script which loads real test data, scales it, and executes inference:

```bash
python scripts/smoke_test_lstm.py
```
