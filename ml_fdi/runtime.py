"""Runtime, shadow-mode inference for the persisted ML anomaly model.

This module deliberately produces monitoring diagnostics only.  It never
changes deterministic FDI decisions or EKF state.
"""
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, List, Tuple

import joblib
from sklearn.ensemble import IsolationForest

from ml_fdi.feature_engineering import FEATURE_COLUMNS, build_features

_MODEL_PATH = Path(__file__).parent / "models" / "sensor_anomaly_model.joblib"


class MLAnomalyMonitor:
    """Loads the existing Isolation Forest and scores navigation records."""

    def __init__(self, model_path: Path = _MODEL_PATH) -> None:
        self.model: IsolationForest = joblib.load(model_path)
        if not isinstance(self.model, IsolationForest):
            raise TypeError(f"Expected IsolationForest, got {type(self.model).__name__}")
        if getattr(self.model, "n_features_in_", None) != len(FEATURE_COLUMNS):
            raise ValueError("Persisted model feature count does not match the 13-feature schema")

    def score_records(self, records: Iterable[Any]) -> List[Tuple[str, float]]:
        rows = [asdict(record) if hasattr(record, "__dataclass_fields__") else dict(record) for record in records]
        features = build_features(rows)
        matrix = [[row[column] for column in FEATURE_COLUMNS] for row in features]
        decisions = self.model.decision_function(matrix)
        predictions = self.model.predict(matrix)
        return [("ANOMALOUS" if prediction == -1 else "NORMAL", float(score))
                for prediction, score in zip(predictions, decisions)]
