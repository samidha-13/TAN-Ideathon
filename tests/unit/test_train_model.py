"""
Unit tests for ml_fdi.train_model.

Tests verify:
  1. Exactly 13 features reach the model.
  2. Healthy-row filtering correctly identifies only non-fault rows.
  3. Fault labels are NOT included in the feature matrix (leakage check).
  4. Truth fields are NOT included in the feature matrix.
  5. FDI outputs are NOT included in the feature matrix.
  6. Timestamp and mission_index are NOT included.
  7. Model trains successfully on healthy data.
  8. Model saves successfully to disk.
  9. Saved model reloads successfully and produces identical predictions.
 10. Feature ordering remains identical after reload.
 11. Evaluation metrics and confusion matrix compute correctly.
 12. Source CSV and JSON files remain unmodified.
 13. Persisted production model artifact exists and meets metadata specification.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

# Ensure repository root is on sys.path
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ml_fdi.feature_engineering import FEATURE_COLUMNS
from ml_fdi.train_model import (
    MISSION_NAMES,
    DEFAULT_MODEL_DIR,
    MODEL_FILENAME,
    METADATA_FILENAME,
    classify_fault_entry,
    is_healthy_entry,
    verify_feature_matrix_safety,
    to_feature_matrix,
    train_isolation_forest,
    save_model_and_metadata,
    load_trained_model,
    compute_binary_metrics,
    evaluate_trained_model,
    load_mission_dataset,
)


def _compute_file_hash(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class TestTrainModelDataIntegrity(unittest.TestCase):
    """Tests for schema, leakage protection, and healthy row selection."""

    def test_exact_13_features_reach_model(self):
        """Feature matrix must have exactly 13 columns in canonical order."""
        self.assertEqual(len(FEATURE_COLUMNS), 13)
        dummy_row = {col: 1.0 for col in FEATURE_COLUMNS}
        matrix = to_feature_matrix([dummy_row])
        self.assertEqual(len(matrix), 1)
        self.assertEqual(len(matrix[0]), 13)

    def test_healthy_row_filtering(self):
        """Only timesteps with all sensors normal must be classified as healthy."""
        healthy_sample = {
            "timestamp": 0.0,
            "gnss_status": "AVAILABLE",
            "radar_status": "VALID",
            "magnetometer_status": "VALID",
        }
        self.assertTrue(is_healthy_entry(healthy_sample))
        self.assertEqual(classify_fault_entry(healthy_sample), "HEALTHY")

        gnss_fault = dict(healthy_sample, gnss_status="DENIED")
        self.assertFalse(is_healthy_entry(gnss_fault))
        self.assertEqual(classify_fault_entry(gnss_fault), "GNSS_DENIAL")

        radar_fault = dict(healthy_sample, radar_status="INVALID")
        self.assertFalse(is_healthy_entry(radar_fault))
        self.assertEqual(classify_fault_entry(radar_fault), "RADAR_FAULT")

        mag_fault = dict(healthy_sample, magnetometer_status="INVALID")
        self.assertFalse(is_healthy_entry(mag_fault))
        self.assertEqual(classify_fault_entry(mag_fault), "MAGNETOMETER_FAULT")

        comb_fault = dict(healthy_sample, gnss_status="DENIED", radar_status="INVALID")
        self.assertFalse(is_healthy_entry(comb_fault))
        self.assertEqual(classify_fault_entry(comb_fault), "COMBINED_FAULT")

    def test_fault_labels_not_in_feature_matrix(self):
        """Fault label keys must trigger a critical leakage error."""
        for forbidden_key in ["gnss_status", "radar_status", "magnetometer_status", "is_fault", "fault_type"]:
            bad_row = {col: 1.0 for col in FEATURE_COLUMNS}
            bad_row[forbidden_key] = 1.0
            with self.assertRaises((ValueError, AssertionError)):
                verify_feature_matrix_safety([bad_row])

    def test_truth_fields_not_included(self):
        """Truth fields must trigger a critical leakage error."""
        for truth_key in ["truth_lat", "truth_lon", "error_lat_m", "error_lon_m", "error_3d_m", "latitude", "longitude"]:
            bad_row = {col: 1.0 for col in FEATURE_COLUMNS}
            bad_row[truth_key] = 10.0
            with self.assertRaises((ValueError, AssertionError)):
                verify_feature_matrix_safety([bad_row])

    def test_fdi_outputs_not_included(self):
        """FDI outputs must trigger a critical leakage error."""
        for fdi_key in ["fdi_radar", "fdi_gnss", "fdi_mag"]:
            bad_row = {col: 1.0 for col in FEATURE_COLUMNS}
            bad_row[fdi_key] = 1.0
            with self.assertRaises((ValueError, AssertionError)):
                verify_feature_matrix_safety([bad_row])

    def test_timestamp_and_mission_index_forbidden(self):
        """Timestamp and mission index must trigger a leakage error."""
        for key in ["timestamp", "mission_index"]:
            bad_row = {col: 1.0 for col in FEATURE_COLUMNS}
            bad_row[key] = 0.0
            with self.assertRaises((ValueError, AssertionError)):
                verify_feature_matrix_safety([bad_row])


class TestIsolationForestTrainingAndPersistence(unittest.TestCase):
    """Tests for model training, saving, loading, and prediction stability."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_model_trains_successfully(self):
        """Isolation Forest fits on valid 13-feature synthetic healthy data."""
        X_synthetic = [[0.5, 1.0, 1.0, 2.0, 2.0, 1.0, 0.01, -0.01, 0.0001, 0.0001, 2.0, 0.5, 0.0] for _ in range(50)]
        model = train_isolation_forest(X_synthetic, n_estimators=10, random_state=42)
        self.assertIsNotNone(model)
        preds = model.predict(X_synthetic)
        self.assertEqual(len(preds), 50)
        # All predictions must be 1 (inlier) or -1 (outlier)
        for p in preds:
            self.assertIn(p, [1, -1])

    def test_model_saves_and_reloads_successfully(self):
        """Persisted model and metadata reload identically."""
        X_synthetic = [[float(i % 5) for _ in range(13)] for i in range(40)]
        model = train_isolation_forest(X_synthetic, n_estimators=10, random_state=42)
        meta = {
            "model_type": "sklearn.ensemble.IsolationForest",
            "n_estimators": 10,
            "feature_names": list(FEATURE_COLUMNS),
            "healthy_training_sample_count": 40,
        }

        m_path, meta_path = save_model_and_metadata(model, meta, model_dir=self.temp_dir)
        self.assertTrue(os.path.isfile(m_path))
        self.assertTrue(os.path.isfile(meta_path))

        reloaded_model, reloaded_meta = load_trained_model(model_dir=self.temp_dir)
        orig_preds = model.predict(X_synthetic)
        reloaded_preds = reloaded_model.predict(X_synthetic)
        self.assertEqual(list(orig_preds), list(reloaded_preds))
        self.assertEqual(reloaded_meta["feature_names"], list(FEATURE_COLUMNS))

    def test_feature_ordering_identical_after_reload(self):
        """Feature ordering in metadata matches canonical FEATURE_COLUMNS exactly."""
        meta = {
            "model_type": "sklearn.ensemble.IsolationForest",
            "feature_names": list(FEATURE_COLUMNS),
        }
        X_synthetic = [[0.0] * 13 for _ in range(20)]
        model = train_isolation_forest(X_synthetic, n_estimators=5, random_state=42)
        save_model_and_metadata(model, meta, model_dir=self.temp_dir)

        _, reloaded_meta = load_trained_model(model_dir=self.temp_dir)
        self.assertEqual(tuple(reloaded_meta["feature_names"]), FEATURE_COLUMNS)

    def test_metadata_rejects_leakage(self):
        """Metadata containing sensitive fields must be rejected."""
        model = train_isolation_forest([[0.0] * 13 for _ in range(10)], n_estimators=5)
        bad_meta = {"truth_lat": 26.5}
        with self.assertRaises(ValueError):
            save_model_and_metadata(model, bad_meta, model_dir=self.temp_dir)


class TestEvaluationMetrics(unittest.TestCase):
    """Tests for metric calculations and confusion matrix."""

    def test_binary_metrics_computation(self):
        """Verify precision, recall, F1, and confusion matrix arithmetic."""
        # Ground truth: 2 healthy (0), 2 fault (1)
        y_true = [0, 0, 1, 1]
        # Predicted: [0, 1, 0, 1] -> TN=1, FP=1, FN=1, TP=1
        y_pred = [0, 1, 0, 1]

        res = compute_binary_metrics(y_true, y_pred)
        cm = res["confusion_matrix"]
        self.assertEqual(cm["TN"], 1)
        self.assertEqual(cm["FP"], 1)
        self.assertEqual(cm["FN"], 1)
        self.assertEqual(cm["TP"], 1)
        self.assertAlmostEqual(res["precision"], 0.5)
        self.assertAlmostEqual(res["recall"], 0.5)
        self.assertAlmostEqual(res["f1"], 0.5)
        self.assertAlmostEqual(res["anomaly_rate"], 0.5)


class TestSourceDataImmutability(unittest.TestCase):
    """Verify that source CSV and JSON files are not touched by the pipeline."""

    def test_source_files_remain_unmodified(self):
        """Hashes of all export CSVs and mission faults.json must match before and after."""
        files_to_check = []
        for m in MISSION_NAMES:
            csv_path = os.path.join(_REPO_ROOT, "data", "exports", f"{m}_records.csv")
            faults_path = os.path.join(_REPO_ROOT, "data", "missions", m, "faults.json")
            files_to_check.extend([csv_path, faults_path])

        initial_hashes = {p: _compute_file_hash(p) for p in files_to_check}

        # Load data through loader
        for m in MISSION_NAMES:
            records, faults = load_mission_dataset(m, repo_root=_REPO_ROOT)
            self.assertGreater(len(records), 0)
            self.assertGreater(len(faults), 0)

        post_hashes = {p: _compute_file_hash(p) for p in files_to_check}
        for p in files_to_check:
            self.assertEqual(
                initial_hashes[p],
                post_hashes[p],
                f"Source file was modified: {p}",
            )


class TestProductionArtifacts(unittest.TestCase):
    """Verify production artifacts saved in ml_fdi/models/."""

    def test_saved_artifacts_exist_and_valid(self):
        """Model joblib and metadata json must exist and be valid."""
        model_path = os.path.join(DEFAULT_MODEL_DIR, MODEL_FILENAME)
        meta_path = os.path.join(DEFAULT_MODEL_DIR, METADATA_FILENAME)

        self.assertTrue(os.path.isfile(model_path), f"Missing {model_path}")
        self.assertTrue(os.path.isfile(meta_path), f"Missing {meta_path}")

        model, meta = load_trained_model(DEFAULT_MODEL_DIR)
        self.assertIsNotNone(model)
        self.assertEqual(meta["model_type"], "sklearn.ensemble.IsolationForest")
        self.assertEqual(meta["n_estimators"], 200)
        self.assertEqual(meta["contamination"], "auto")
        self.assertEqual(meta["random_state"], 42)
        self.assertEqual(meta["healthy_training_sample_count"], 12476)
        self.assertEqual(tuple(meta["feature_names"]), FEATURE_COLUMNS)

        # Check prediction on 13 features runs
        test_vector = [[0.0] * 13]
        pred = model.predict(test_vector)
        self.assertIn(pred[0], [1, -1])


if __name__ == "__main__":
    unittest.main()
