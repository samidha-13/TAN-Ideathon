"""
Feature engineering for ML-assisted FDI (shadow mode).

Extracts exactly 13 ML-safe features from navigation export CSVs.
All features are derived from navigation estimates and sensor diagnostics.
No ground truth, no FDI outputs, no future data are used.

Features (13 total)
-------------------
Base (6):
  1. tan_match_score        – TAN terrain-match quality (0–1; 0 when invalid)
  2. tan_valid              – Whether TAN produced valid measurement (0/1)
  3. terrain_obs_ordinal    – Terrain observability (LOW=0, MEDIUM=1, HIGH=2)
  4. uncertainty_lat_m      – EKF latitude uncertainty, 1-sigma (m)
  5. uncertainty_lon_m      – EKF longitude uncertainty, 1-sigma (m)
  6. uncertainty_alt_m      – EKF altitude uncertainty, 1-sigma (m)

Derived temporal (7, strictly causal — no future rows):
  7.  delta_unc_lat             – uncertainty_lat_m[t] − uncertainty_lat_m[t−1]
  8.  delta_unc_lon             – uncertainty_lon_m[t] − uncertainty_lon_m[t−1]
  9.  delta_est_lat             – estimated_lat[t] − estimated_lat[t−1]
  10. delta_est_lon             – estimated_lon[t] − estimated_lon[t−1]
  11. rolling_mean_unc_lat_10   – mean of uncertainty_lat_m over past 10 steps
  12. rolling_mean_tan_score_10 – mean of tan_match_score over past 10 steps
  13. unc_change_rate           – (delta_unc_lat + delta_unc_lon) / 2

NaN Handling
------------
  - tan_match_score : NaN/non-finite → 0.0
    Rationale: the export CSV already writes 0.0 when TAN is invalid.
    A NaN here would indicate a data error; 0.0 is the conservative
    equivalent (no match = lowest possible score).

  - tan_valid : non-parseable → 0.0 (False)
    Rationale: if the field cannot be read, the safest assumption is
    that TAN is not valid.

  - terrain_obs : unrecognised string → 0 (LOW)
    Rationale: "N/A" legitimately occurs when radar is not accepted
    and observability was not computed.  Treating this as LOW is
    consistent with the navigation pipeline's behaviour (TAN is
    rejected when observability is LOW).

  - uncertainty_lat_m, uncertainty_lon_m, uncertainty_alt_m :
    NaN/non-finite → 0.0
    Rationale: these are always finite in valid export data (they come
    from the EKF covariance diagonal).  A NaN would indicate a data
    error; 0.0 is conservative (zero uncertainty).

  - estimated_lat, estimated_lon : NaN/non-finite → 0.0
    Rationale: these are always finite in valid export data.  They are
    used only to compute deltas (delta_est_lat, delta_est_lon) — the
    raw values never appear in the output feature set.  A NaN-to-0.0
    replacement would produce a visible spike in the delta, which is
    acceptable (it signals an anomalous input).

  - delta features : first row → 0.0
    Rationale: there is no t−1 for the first row.  0.0 means "no
    change from previous step", which is the neutral value.

  - rolling mean features : first rows use min_periods=1
    Rationale: the rolling window grows from 1 to 10 over the first
    10 rows.  Each row uses only itself and preceding rows.  No future
    data is ever accessed.

Source Columns Read (but NOT emitted as features)
-------------------------------------------------
  - estimated_lat, estimated_lon : used ONLY to compute delta_est_lat
    and delta_est_lon.  The raw position values are excluded from the
    output feature set because they are mission-dependent and do not
    carry per-step anomaly information.

Forbidden Columns (never used as ML features)
----------------------------------------------
  truth_lat, truth_lon, error_lat_m, error_lon_m, error_3d_m,
  fdi_radar, fdi_gnss, fdi_mag,
  timestamp, mission_index,
  gnss_accepted, radar_accepted, mag_accepted, sensor_count, nav_mode,
  ins_drift_m, magnav_available, magnav_quality,
  estimated_lat, estimated_lon, estimated_alt

Usage
-----
    from ml_fdi.feature_engineering import build_features, load_mission_features

    # From pre-loaded records (list of dicts from csv.DictReader):
    features = build_features(records)

    # From a CSV file path:
    features = load_mission_features("data/exports/desert_mission_records.csv")
"""

import csv
import math
import os
from typing import List, Dict, Any


# ── Constants ─────────────────────────────────────────────────────────────────

# Exact 13 output feature columns, in canonical order.
FEATURE_COLUMNS = (
    "tan_match_score",
    "tan_valid",
    "terrain_obs_ordinal",
    "uncertainty_lat_m",
    "uncertainty_lon_m",
    "uncertainty_alt_m",
    "delta_unc_lat",
    "delta_unc_lon",
    "delta_est_lat",
    "delta_est_lon",
    "rolling_mean_unc_lat_10",
    "rolling_mean_tan_score_10",
    "unc_change_rate",
)

# Columns that MUST NEVER appear in the output feature vector.
FORBIDDEN_COLUMNS = frozenset({
    # Ground truth
    "truth_lat", "truth_lon",
    # Truth-derived error metrics
    "error_lat_m", "error_lon_m", "error_3d_m",
    # Deterministic FDI outputs (label leakage)
    "fdi_radar", "fdi_gnss", "fdi_mag",
    # Other excluded per specification
    "timestamp", "mission_index",
    "gnss_accepted", "radar_accepted", "mag_accepted",
    "sensor_count", "nav_mode",
    "ins_drift_m",
    "magnav_available", "magnav_quality",
    "estimated_lat", "estimated_lon", "estimated_alt",
})

# Source columns required from the export CSV to compute the 13 features.
# Note: estimated_lat and estimated_lon are READ for delta computation but
# are NOT emitted as output features.
_REQUIRED_SOURCE_COLUMNS = frozenset({
    "tan_match_score",
    "tan_valid",
    "terrain_obs",
    "uncertainty_lat_m",
    "uncertainty_lon_m",
    "uncertainty_alt_m",
    "estimated_lat",
    "estimated_lon",
})

# Terrain observability ordinal encoding.
_TERRAIN_OBS_MAP = {
    "LOW": 0.0,
    "MEDIUM": 1.0,
    "HIGH": 2.0,
    "N/A": 0.0,   # N/A occurs when radar is not accepted → treat as LOW
}

_ROLLING_WINDOW = 10


# ── Public API ────────────────────────────────────────────────────────────────

def build_features(records: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    """
    Build exactly 13 ML-safe features from navigation records.

    Parameters
    ----------
    records : list of dict
        Rows from a **single** mission's ``*_records.csv`` export.
        Each dict must contain at least the columns listed in
        ``_REQUIRED_SOURCE_COLUMNS``.  The list must come from a
        single mission — temporal features are computed within this
        list and must not cross mission boundaries.

    Returns
    -------
    list of dict
        Same number of rows as *records*.  Each dict has exactly 13
        keys matching ``FEATURE_COLUMNS``.  All values are ``float``.

    Raises
    ------
    ValueError
        If required source columns are missing from the input.
    AssertionError
        If the output fails internal validation (wrong column count,
        forbidden column detected, non-numeric value, NaN/Inf value).

    Notes
    -----
    The input *records* list is NOT modified in place.  A new list of
    dicts is returned.
    """
    _validate_input_schema(records)

    n = len(records)
    if n == 0:
        return []

    # ── 1. Extract source columns as float arrays ─────────────────────────
    tan_score = _extract_float_column(records, "tan_match_score", default=0.0)
    tan_valid = _extract_bool_column(records, "tan_valid")
    terrain_obs = _extract_terrain_obs_column(records)
    unc_lat = _extract_float_column(records, "uncertainty_lat_m", default=0.0)
    unc_lon = _extract_float_column(records, "uncertainty_lon_m", default=0.0)
    unc_alt = _extract_float_column(records, "uncertainty_alt_m", default=0.0)
    est_lat = _extract_float_column(records, "estimated_lat", default=0.0)
    est_lon = _extract_float_column(records, "estimated_lon", default=0.0)

    # ── 2. Compute temporal features (strictly causal, single mission) ────
    d_unc_lat = _one_step_delta(unc_lat)
    d_unc_lon = _one_step_delta(unc_lon)
    d_est_lat = _one_step_delta(est_lat)
    d_est_lon = _one_step_delta(est_lon)

    rm_unc_lat = _causal_rolling_mean(unc_lat, _ROLLING_WINDOW)
    rm_tan_score = _causal_rolling_mean(tan_score, _ROLLING_WINDOW)

    unc_rate = [
        (d_unc_lat[i] + d_unc_lon[i]) / 2.0
        for i in range(n)
    ]

    # ── 3. Assemble output rows ───────────────────────────────────────────
    features: List[Dict[str, float]] = []
    for i in range(n):
        row = {
            "tan_match_score":          tan_score[i],
            "tan_valid":                tan_valid[i],
            "terrain_obs_ordinal":      terrain_obs[i],
            "uncertainty_lat_m":        unc_lat[i],
            "uncertainty_lon_m":        unc_lon[i],
            "uncertainty_alt_m":        unc_alt[i],
            "delta_unc_lat":            d_unc_lat[i],
            "delta_unc_lon":            d_unc_lon[i],
            "delta_est_lat":            d_est_lat[i],
            "delta_est_lon":            d_est_lon[i],
            "rolling_mean_unc_lat_10":  rm_unc_lat[i],
            "rolling_mean_tan_score_10": rm_tan_score[i],
            "unc_change_rate":          unc_rate[i],
        }
        features.append(row)

    # ── 4. Final validation ───────────────────────────────────────────────
    _validate_output(features)

    return features


def load_mission_features(csv_path: str) -> List[Dict[str, float]]:
    """
    Load a mission export CSV and return exactly 13 ML features.

    Parameters
    ----------
    csv_path : str
        Path to a single mission's ``*_records.csv`` export file
        (e.g. ``data/exports/desert_mission_records.csv``).

    Returns
    -------
    list of dict
        Same row count as the CSV.  Each dict has exactly 13 keys.

    Raises
    ------
    FileNotFoundError
        If the CSV file does not exist.
    """
    records = _load_csv(csv_path)
    return build_features(records)


# ── Column extraction helpers ─────────────────────────────────────────────────

def _extract_float_column(
    records: List[Dict[str, Any]],
    col: str,
    default: float = 0.0,
) -> List[float]:
    """
    Extract a column as a list of floats.

    NaN, Inf, and unparseable values are replaced with *default*.
    """
    result = []
    for row in records:
        raw = row.get(col)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            val = default
        if not math.isfinite(val):
            val = default
        result.append(val)
    return result


def _extract_bool_column(
    records: List[Dict[str, Any]],
    col: str,
) -> List[float]:
    """
    Extract a boolean column as a list of 0.0 / 1.0 floats.

    Accepts ``True``/``False`` (bool), ``"True"``/``"False"`` (str),
    and ``1``/``0`` (int/float).
    """
    result = []
    for row in records:
        raw = row.get(col, "False")
        if isinstance(raw, bool):
            result.append(1.0 if raw else 0.0)
        elif isinstance(raw, str):
            result.append(1.0 if raw.strip().lower() == "true" else 0.0)
        elif isinstance(raw, (int, float)):
            result.append(1.0 if raw else 0.0)
        else:
            result.append(0.0)
    return result


def _extract_terrain_obs_column(
    records: List[Dict[str, Any]],
) -> List[float]:
    """
    Extract ``terrain_obs`` as ordinal floats.

    Encoding: LOW → 0.0, MEDIUM → 1.0, HIGH → 2.0, N/A → 0.0.
    Unrecognised values → 0.0 (treated as LOW).
    """
    result = []
    for row in records:
        raw = str(row.get("terrain_obs", "LOW")).strip().upper()
        result.append(_TERRAIN_OBS_MAP.get(raw, 0.0))
    return result


# ── Temporal feature helpers ──────────────────────────────────────────────────

def _one_step_delta(values: List[float]) -> List[float]:
    """
    Compute one-step backward difference: ``values[t] − values[t−1]``.

    The first element is always 0.0 (no predecessor).
    This is strictly causal — only the current and immediately
    preceding value are used.
    """
    n = len(values)
    if n == 0:
        return []
    deltas = [0.0]  # t=0: no previous value → delta = 0
    for i in range(1, n):
        deltas.append(values[i] - values[i - 1])
    return deltas


def _causal_rolling_mean(
    values: List[float],
    window: int,
) -> List[float]:
    """
    Compute a strictly causal rolling mean.

    For row t, the mean is computed over::

        values[max(0, t − window + 1) : t + 1]

    This uses only the current row and up to ``window − 1`` preceding
    rows.  No future rows are ever accessed.  The effective window
    size grows from 1 to *window* over the first *window* rows
    (min_periods=1 behaviour).
    """
    n = len(values)
    result = []

    # Running sum for O(n) computation
    cumsum = 0.0
    for i in range(n):
        cumsum += values[i]
        start = i - window + 1
        if start > 0:
            cumsum -= values[start - 1]
            count = window
        else:
            count = i + 1
        result.append(cumsum / count)

    # Recompute without running sum to avoid float drift
    # (the above has subtle bugs with running subtraction;
    #  use the simple version for correctness)
    result_safe = []
    for i in range(n):
        lo = max(0, i - window + 1)
        window_vals = values[lo: i + 1]
        result_safe.append(sum(window_vals) / len(window_vals))

    return result_safe


# ── Input / output validation ─────────────────────────────────────────────────

def _validate_input_schema(records: List[Dict[str, Any]]) -> None:
    """
    Verify that the input records contain all required source columns.

    Raises ValueError if any required column is missing.
    """
    if not records:
        return
    available = set(records[0].keys())
    missing = _REQUIRED_SOURCE_COLUMNS - available
    if missing:
        raise ValueError(
            f"Missing required source columns: {sorted(missing)}.  "
            f"Available columns: {sorted(available)}"
        )


def _validate_output(features: List[Dict[str, float]]) -> None:
    """
    Validate the final feature output.

    Checks:
      1. Exactly 13 feature columns.
      2. Column names match FEATURE_COLUMNS exactly.
      3. No forbidden column is present.
      4. All values are finite floats (no NaN, no Inf).
    """
    if not features:
        return

    cols = set(features[0].keys())
    expected = set(FEATURE_COLUMNS)

    # Check column set matches
    if cols != expected:
        extra = cols - expected
        missing_cols = expected - cols
        raise AssertionError(
            f"Feature output column mismatch.  "
            f"Extra: {sorted(extra)}, Missing: {sorted(missing_cols)}"
        )

    # Check count
    if len(cols) != 13:
        raise AssertionError(
            f"Expected exactly 13 feature columns, got {len(cols)}"
        )

    # Check no forbidden column leaked in
    leaked = cols & FORBIDDEN_COLUMNS
    if leaked:
        raise AssertionError(
            f"FORBIDDEN columns found in feature output: {sorted(leaked)}"
        )

    # Check all values are finite numbers
    for i, row in enumerate(features):
        for col, val in row.items():
            if not isinstance(val, (int, float)):
                raise AssertionError(
                    f"Non-numeric value at row {i}, column '{col}': "
                    f"{val!r} (type={type(val).__name__})"
                )
            if math.isnan(val) or math.isinf(val):
                raise AssertionError(
                    f"NaN or Inf at row {i}, column '{col}': {val}"
                )


# ── CSV loader ────────────────────────────────────────────────────────────────

def _load_csv(path: str) -> List[Dict[str, str]]:
    """
    Load a CSV file as a list of dicts.

    Matches the csv.DictReader pattern used throughout this project.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"CSV not found: {path}")
    rows: List[Dict[str, str]] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows
