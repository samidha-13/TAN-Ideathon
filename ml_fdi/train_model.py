"""
Training and evaluation pipeline for ML-assisted FDI Isolation Forest.

Trains an unsupervised Isolation Forest model on healthy navigation baseline data
from all four missions:
  - desert_mission
  - mountain_mission
  - western_ghats_mission
  - flat_plain_mission

Strict Change Control & Security Rules:
  1. Only healthy rows (no active injected faults in faults.json) are used for training.
  2. Ground-truth fault labels are NEVER used as features.
  3. No truth positions, navigation errors, FDI outputs, timestamps, or mission indices
     are allowed in the feature matrix.
  4. Features are built strictly through ml_fdi.feature_engineering.build_features().
  5. The model operates in SHADOW MODE / offline evaluation only. It does not alter navigation.
"""

import csv
import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import joblib
import sklearn
from sklearn.ensemble import IsolationForest

# Ensure repository root is on sys.path
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ml_fdi.feature_engineering import (
    FEATURE_COLUMNS,
    FORBIDDEN_COLUMNS,
    build_features,
)

# ── Mission List & Default Paths ──────────────────────────────────────────────

MISSION_NAMES = (
    "desert_mission",
    "mountain_mission",
    "western_ghats_mission",
    "flat_plain_mission",
)

DEFAULT_MODEL_DIR = os.path.join(_REPO_ROOT, "ml_fdi", "models")
MODEL_FILENAME = "sensor_anomaly_model.joblib"
METADATA_FILENAME = "model_metadata.json"

# Extended forbidden keys that must NEVER enter feature matrices or model inputs
FORBIDDEN_INPUT_KEYS = frozenset(FORBIDDEN_COLUMNS | {
    "gnss_status",
    "radar_status",
    "magnetometer_status",
    "fault_type",
    "is_fault",
    "y_true",
    "label",
    "latitude",
    "longitude",
})


# ── Fault Classification Helper ───────────────────────────────────────────────

def classify_fault_entry(fault_entry: Dict[str, Any]) -> str:
    """
    Classify a single timestep's fault status from faults.json.

    Returns one of:
      - "HEALTHY"
      - "GNSS_DENIAL"
      - "RADAR_FAULT"
      - "MAGNETOMETER_FAULT"
      - "COMBINED_FAULT"
    """
    gnss_fault = fault_entry.get("gnss_status") != "AVAILABLE"
    radar_fault = fault_entry.get("radar_status") != "VALID"
    mag_fault = fault_entry.get("magnetometer_status") != "VALID"

    num_faults = sum([gnss_fault, radar_fault, mag_fault])
    if num_faults == 0:
        return "HEALTHY"
    if num_faults > 1:
        return "COMBINED_FAULT"
    if gnss_fault:
        return "GNSS_DENIAL"
    if radar_fault:
        return "RADAR_FAULT"
    return "MAGNETOMETER_FAULT"


def is_healthy_entry(fault_entry: Dict[str, Any]) -> bool:
    """Return True if no sensor is in a fault state in this timestep."""
    return (
        fault_entry.get("gnss_status") == "AVAILABLE"
        and fault_entry.get("radar_status") == "VALID"
        and fault_entry.get("magnetometer_status") == "VALID"
    )


# ── Data Loading & Alignment ──────────────────────────────────────────────────

def load_mission_dataset(
    mission_name: str,
    repo_root: str = _REPO_ROOT,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """
    Load records CSV and independent faults.json for a mission.

    Verifies 1:1 row count and timestamp alignment between records and faults.
    Raises ValueError if alignment fails or file is missing.
    """
    csv_path = os.path.join(repo_root, "data", "exports", f"{mission_name}_records.csv")
    faults_path = os.path.join(repo_root, "data", "missions", mission_name, "faults.json")

    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"Export CSV not found: {csv_path}")
    if not os.path.isfile(faults_path):
        raise FileNotFoundError(f"Faults file not found: {faults_path}")

    records: List[Dict[str, str]] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(dict(row))

    with open(faults_path, "r", encoding="utf-8") as f:
        faults: List[Dict[str, Any]] = json.load(f)

    if len(records) != len(faults):
        raise ValueError(
            f"Mission {mission_name} length mismatch: "
            f"{len(records)} records vs {len(faults)} faults"
        )

    # Check timestamp alignment
    for i in range(len(records)):
        t_rec = float(records[i]["timestamp"])
        t_flt = float(faults[i]["timestamp"])
        if abs(t_rec - t_flt) > 1e-4:
            raise ValueError(
                f"Timestamp mismatch in {mission_name} row {i}: "
                f"record={t_rec}, fault={t_flt}"
            )

    return records, faults


# ── Leakage Verification ──────────────────────────────────────────────────────

def verify_feature_matrix_safety(
    features: List[Dict[str, float]],
    context_msg: str = "",
) -> None:
    """
    Strict programmatic data leakage validation.

    Verifies:
      1. Exactly 13 feature columns are present.
      2. Feature names match FEATURE_COLUMNS exactly.
      3. No forbidden column or ground-truth key is present.
      4. All values are finite numbers.

    Raises ValueError or AssertionError immediately if any check fails.
    """
    if not features:
        return

    cols = set(features[0].keys())
    expected = set(FEATURE_COLUMNS)

    if cols != expected:
        extra = cols - expected
        missing = expected - cols
        raise AssertionError(
            f"Feature schema violation [{context_msg}]: "
            f"extra={sorted(extra)}, missing={sorted(missing)}"
        )

    if len(cols) != 13:
        raise AssertionError(
            f"Expected exactly 13 features [{context_msg}], got {len(cols)}"
        )

    forbidden_found = cols & FORBIDDEN_INPUT_KEYS
    if forbidden_found:
        raise ValueError(
            f"CRITICAL LEAKAGE DETECTED [{context_msg}]: "
            f"Forbidden keys in feature set: {sorted(forbidden_found)}"
        )

    # Check that all elements are finite floats
    for i, row in enumerate(features):
        for k, v in row.items():
            if not isinstance(v, (int, float)):
                raise TypeError(
                    f"Non-numeric feature value at row {i}, key '{k}' [{context_msg}]: {v!r}"
                )


def to_feature_matrix(features: List[Dict[str, float]]) -> List[List[float]]:
    """Convert list of feature dicts to 2D list strictly following FEATURE_COLUMNS order."""
    return [[row[col] for col in FEATURE_COLUMNS] for row in features]


# ── Training Pipeline ─────────────────────────────────────────────────────────

def train_isolation_forest(
    X_train: List[List[float]],
    n_estimators: int = 200,
    contamination: str = "auto",
    random_state: int = 42,
    n_jobs: int = -1,
) -> IsolationForest:
    """
    Fit an IsolationForest model on the provided training samples.

    Must be called ONLY with healthy training baseline samples.
    """
    if len(X_train) == 0:
        raise ValueError("Cannot train IsolationForest on empty dataset.")

    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=n_jobs,
    )
    model.fit(X_train)
    return model


def save_model_and_metadata(
    model: IsolationForest,
    metadata: Dict[str, Any],
    model_dir: str = DEFAULT_MODEL_DIR,
) -> Tuple[str, str]:
    """
    Save trained model (.joblib) and metadata (.json) to disk.

    Ensures target directory exists. Does NOT save ground truth or fault data.
    """
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, MODEL_FILENAME)
    meta_path = os.path.join(model_dir, METADATA_FILENAME)

    # Verify metadata does not contain sensitive leakage
    forbidden_meta = {"truth_lat", "truth_lon", "faults", "fdi_radar", "error_3d_m"}
    meta_keys = set(metadata.keys())
    if meta_keys & forbidden_meta:
        raise ValueError(f"Forbidden keys in metadata: {meta_keys & forbidden_meta}")

    joblib.dump(model, model_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return model_path, meta_path


def load_trained_model(
    model_dir: str = DEFAULT_MODEL_DIR,
) -> Tuple[IsolationForest, Dict[str, Any]]:
    """Load the persisted model and metadata from disk."""
    model_path = os.path.join(model_dir, MODEL_FILENAME)
    meta_path = os.path.join(model_dir, METADATA_FILENAME)

    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(f"Metadata file not found: {meta_path}")

    model: IsolationForest = joblib.load(model_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata: Dict[str, Any] = json.load(f)

    return model, metadata


# ── Comprehensive Evaluation ──────────────────────────────────────────────────

def compute_binary_metrics(
    y_true: List[int],
    y_pred: List[int],
) -> Dict[str, Any]:
    """
    Compute binary classification metrics where 1 = Fault / Anomaly, 0 = Healthy / Normal.

    y_true: 1 if ground truth has an active fault, 0 if healthy
    y_pred: 1 if Isolation Forest predicted anomaly, 0 if normal
    """
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

    total = len(y_true)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    anomaly_rate = sum(y_pred) / total if total > 0 else 0.0

    return {
        "total": total,
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "anomaly_rate": anomaly_rate,
        "confusion_matrix": {
            "TN": tn, "FP": fp,
            "FN": fn, "TP": tp,
        },
    }


def evaluate_trained_model(
    model: IsolationForest,
    all_mission_data: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Evaluate the trained model across all missions and fault types.

    Does NOT retrain the model.
    """
    overall_y_true: List[int] = []
    overall_y_pred: List[int] = []

    per_mission_metrics: Dict[str, Dict[str, Any]] = {}
    fault_type_samples: Dict[str, Dict[str, int]] = {
        "HEALTHY": {"total": 0, "anomalies": 0},
        "GNSS_DENIAL": {"total": 0, "anomalies": 0},
        "RADAR_FAULT": {"total": 0, "anomalies": 0},
        "MAGNETOMETER_FAULT": {"total": 0, "anomalies": 0},
        "COMBINED_FAULT": {"total": 0, "anomalies": 0},
    }

    for mission_name, data in all_mission_data.items():
        X = data["X"]
        faults = data["faults"]

        # IsolationForest predict: 1 for inlier (normal), -1 for outlier (anomaly)
        preds = model.predict(X)
        y_pred_mission = [1 if p == -1 else 0 for p in preds]
        y_true_mission = [0 if is_healthy_entry(flt) else 1 for flt in faults]

        m_metrics = compute_binary_metrics(y_true_mission, y_pred_mission)
        per_mission_metrics[mission_name] = m_metrics

        overall_y_true.extend(y_true_mission)
        overall_y_pred.extend(y_pred_mission)

        # Track per-fault-type anomaly detection rates
        for flt, yp in zip(faults, y_pred_mission):
            ftype = classify_fault_entry(flt)
            fault_type_samples[ftype]["total"] += 1
            if yp == 1:
                fault_type_samples[ftype]["anomalies"] += 1

    overall_metrics = compute_binary_metrics(overall_y_true, overall_y_pred)

    per_fault_type_metrics = {}
    for ftype, counts in fault_type_samples.items():
        tot = counts["total"]
        anom = counts["anomalies"]
        rate = anom / tot if tot > 0 else 0.0
        per_fault_type_metrics[ftype] = {
            "total_samples": tot,
            "detected_anomalies": anom,
            "anomaly_rate": rate,
        }

    return {
        "overall": overall_metrics,
        "per_mission": per_mission_metrics,
        "per_fault_type": per_fault_type_metrics,
    }


def format_evaluation_report(results: Dict[str, Any], meta: Dict[str, Any]) -> str:
    """Format evaluation statistics into a clean text report."""
    ov = results["overall"]
    pm = results["per_mission"]
    pf = results["per_fault_type"]
    cm = ov["confusion_matrix"]

    lines = [
        "=" * 70,
        "ML-ASSISTED FDI -- OFFLINE ISOLATION FOREST EVALUATION REPORT",
        "=" * 70,
        f"Model Type:                 {meta.get('model_type')}",
        f"Number of Estimators:       {meta.get('n_estimators')}",
        f"Contamination Parameter:    {meta.get('contamination')}",
        f"Random State:               {meta.get('random_state')}",
        f"Scikit-Learn Version:       {meta.get('sklearn_version')}",
        f"Healthy Training Samples:   {meta.get('healthy_training_sample_count')}",
        f"Features Used (exact 13):   {', '.join(meta.get('feature_names', []))}",
        "-" * 70,
        "OVERALL PERFORMANCE METRICS (Total Rows: %d)" % ov["total"],
        "-" * 70,
        f"  Total Healthy Rows:       {ov['true_negatives'] + ov['false_positives']}",
        f"  Total Fault Rows:         {ov['true_positives'] + ov['false_negatives']}",
        f"  Overall Precision:        {ov['precision']:.4f} ({ov['precision']*100:.2f}%)",
        f"  Overall Recall:           {ov['recall']:.4f} ({ov['recall']*100:.2f}%)",
        f"  Overall F1 Score:         {ov['f1']:.4f}",
        f"  Overall Anomaly Rate:     {ov['anomaly_rate']:.4f} ({ov['anomaly_rate']*100:.2f}%)",
        "",
        "CONFUSION MATRIX:",
        "  True Negatives  (TN - Healthy correct):  %d" % cm["TN"],
        "  False Positives (FP - False alarm):      %d (FPR: %.2f%%)" % (
            cm["FP"], (cm["FP"] / (cm["TN"] + cm["FP"]) * 100) if (cm["TN"] + cm["FP"]) > 0 else 0
        ),
        "  False Negatives (FN - Fault missed):     %d" % cm["FN"],
        "  True Positives  (TP - Fault detected):   %d" % cm["TP"],
        "-" * 70,
        "PER-MISSION PERFORMANCE:",
        "-" * 70,
    ]

    for m_name, m_res in pm.items():
        lines.extend([
            f"  [{m_name}]",
            f"    Total: {m_res['total']} | Healthy: {m_res['true_negatives'] + m_res['false_positives']} | Fault: {m_res['true_positives'] + m_res['false_negatives']}",
            f"    Precision: {m_res['precision']:.4f} | Recall: {m_res['recall']:.4f} | F1: {m_res['f1']:.4f}",
            f"    Confusion Matrix: TN={m_res['true_negatives']}, FP={m_res['false_positives']}, FN={m_res['false_negatives']}, TP={m_res['true_positives']}",
        ])

    lines.extend([
        "-" * 70,
        "PER-FAULT-TYPE ANOMALY DETECTION RATES:",
        "-" * 70,
    ])

    for ftype, f_res in pf.items():
        lines.append(
            f"  {ftype:<20}: {f_res['detected_anomalies']:>4} / {f_res['total_samples']:>5} "
            f"anomalous (Detection Rate: {f_res['anomaly_rate']*100:6.2f}%)"
        )

    lines.extend([
        "=" * 70,
        "PROTOTYPE LIMITATION & SCOPE NOTICES:",
        "  1. SENSORS COVERED: Evaluated on simulated GNSS denial, radar altimeter failure,",
        "     magnetometer interference, and combined failures.",
        "  2. IDENTICAL FAULT TIMING LIMITATION: Faults in the simulator dataset are injected",
        "     at identical mission time offsets across runs (10-20s, 30-40s, 50-60s, 70-80s).",
        "     Neither timestamp nor mission_index was exposed to the model to prevent",
        "     temporal overfitting.",
        "  3. NON-OVERCLAIM NOTICE: This model is a simulator-validated prototype under",
        "     shadow mode. It is NOT aircraft-certified and does NOT replace deterministic FDI.",
        "  4. GENERAL ANOMALY MONITOR: The Isolation Forest scores general anomalous dynamics.",
        "     It does not isolate individual failing physical sensors (FDI retains isolation).",
        "=" * 70,
    ])

    return "\n".join(lines)


# ── Full Execution Orchestrator ───────────────────────────────────────────────

def run_training_and_evaluation(
    repo_root: str = _REPO_ROOT,
    model_dir: str = DEFAULT_MODEL_DIR,
    n_estimators: int = 200,
    contamination: str = "auto",
    random_state: int = 42,
    n_jobs: int = -1,
) -> Tuple[IsolationForest, Dict[str, Any], Dict[str, Any], str]:
    """
    Execute the entire offline training and evaluation workflow.

    Returns (model, metadata, eval_results, report_text).
    """
    all_mission_data: Dict[str, Dict[str, Any]] = {}
    healthy_training_samples: List[List[float]] = []

    for mission_name in MISSION_NAMES:
        records, faults = load_mission_dataset(mission_name, repo_root=repo_root)
        features = build_features(records)

        # Programmatic leakage validation on raw feature output
        verify_feature_matrix_safety(features, context_msg=mission_name)

        X_all = to_feature_matrix(features)

        # Select only healthy rows for model training
        healthy_indices = [i for i, flt in enumerate(faults) if is_healthy_entry(flt)]
        for idx in healthy_indices:
            healthy_training_samples.append(X_all[idx])

        all_mission_data[mission_name] = {
            "records": records,
            "faults": faults,
            "features": features,
            "X": X_all,
            "healthy_indices": healthy_indices,
        }

    # Train Isolation Forest on combined healthy dataset
    model = train_isolation_forest(
        healthy_training_samples,
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=n_jobs,
    )

    metadata: Dict[str, Any] = {
        "model_type": "sklearn.ensemble.IsolationForest",
        "n_estimators": n_estimators,
        "contamination": contamination,
        "random_state": random_state,
        "feature_names": list(FEATURE_COLUMNS),
        "training_missions": list(MISSION_NAMES),
        "healthy_training_sample_count": len(healthy_training_samples),
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__,
    }

    # Save model and metadata
    save_model_and_metadata(model, metadata, model_dir=model_dir)

    # Evaluate across all missions
    eval_results = evaluate_trained_model(model, all_mission_data)
    report_text = format_evaluation_report(eval_results, metadata)

    return model, metadata, eval_results, report_text


if __name__ == "__main__":
    print("Starting ML-Assisted FDI Isolation Forest offline training...")
    model, metadata, eval_results, report = run_training_and_evaluation()
    print("\n" + report)
