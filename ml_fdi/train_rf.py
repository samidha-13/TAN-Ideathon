import os
import json
import datetime
import joblib
import sklearn
from sklearn.ensemble import RandomForestClassifier
from typing import Dict, Any, List, Tuple

from ml_fdi.train_model import (
    MISSION_NAMES, _REPO_ROOT, load_mission_dataset,
    to_feature_matrix, is_healthy_entry, verify_feature_matrix_safety,
    compute_binary_metrics, classify_fault_entry, DEFAULT_MODEL_DIR
)
from ml_fdi.feature_engineering import build_features, FEATURE_COLUMNS

def run_lomo_evaluation():
    all_data = {}
    for mn in MISSION_NAMES:
        records, faults = load_mission_dataset(mn, repo_root=_REPO_ROOT)
        features = build_features(records)
        verify_feature_matrix_safety(features, context_msg=mn)
        X = to_feature_matrix(features)
        y = [0 if is_healthy_entry(f) else 1 for f in faults]
        all_data[mn] = {'X': X, 'y': y, 'faults': faults}
    
    tp, fp, fn, tn = 0, 0, 0, 0
    per_fault_recalls = {
        'GNSS_DENIAL': {'hits': 0, 'total': 0},
        'RADAR_FAULT': {'hits': 0, 'total': 0},
        'MAGNETOMETER_FAULT': {'hits': 0, 'total': 0},
        'COMBINED_FAULT': {'hits': 0, 'total': 0}
    }
    
    for test_mission in MISSION_NAMES:
        X_train, y_train = [], []
        for mn in MISSION_NAMES:
            if mn != test_mission:
                X_train.extend(all_data[mn]['X'])
                y_train.extend(all_data[mn]['y'])
        
        clf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        clf.fit(X_train, y_train)
        
        X_test = all_data[test_mission]['X']
        y_test = all_data[test_mission]['y']
        faults_test = all_data[test_mission]['faults']
        
        preds = clf.predict(X_test)
        
        for yt, yp, flt in zip(y_test, preds, faults_test):
            if yt == 1 and yp == 1: tp += 1
            elif yt == 0 and yp == 1: fp += 1
            elif yt == 1 and yp == 0: fn += 1
            elif yt == 0 and yp == 0: tn += 1
            
            if yt == 1:
                ftype = classify_fault_entry(flt)
                per_fault_recalls[ftype]['total'] += 1
                if yp == 1:
                    per_fault_recalls[ftype]['hits'] += 1

    acc = (tp+tn)/(tp+tn+fp+fn) if (tp+tn+fp+fn) else 0
    prec = tp/(tp+fp) if (tp+fp) else 0
    rec = tp/(tp+fn) if (tp+fn) else 0
    f1 = 2*tp/(2*tp+fp+fn) if (2*tp+fp+fn) else 0

    print('--- Leave-One-Mission-Out Cross-Validation ---')
    print(f'Accuracy: {acc:.4f}')
    print(f'Precision: {prec:.4f}')
    print(f'Recall: {rec:.4f}')
    print(f'F1: {f1:.4f}')
    print('Confusion Matrix:', {'TN': tn, 'FP': fp, 'FN': fn, 'TP': tp})
    print('Per-fault recall:')
    for k, v in per_fault_recalls.items():
        score = (v['hits']/v['total']) if v['total'] > 0 else 0
        print(f'  {k}: {score:.4f}')
    print('------------------------------------------------')

def train_production_model():
    X_train_all, y_train_all = [], []
    for mn in MISSION_NAMES:
        records, faults = load_mission_dataset(mn, repo_root=_REPO_ROOT)
        features = build_features(records)
        X = to_feature_matrix(features)
        y = [0 if is_healthy_entry(f) else 1 for f in faults]
        X_train_all.extend(X)
        y_train_all.extend(y)

    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train_all, y_train_all)

    metadata = {
        'model_type': 'sklearn.ensemble.RandomForestClassifier',
        'n_estimators': 100,
        'random_state': 42,
        'feature_names': list(FEATURE_COLUMNS),
        'training_missions': list(MISSION_NAMES),
        'training_sample_count': len(X_train_all),
        'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sklearn_version': sklearn.__version__,
    }

    model_dir = DEFAULT_MODEL_DIR
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(model_dir, 'rf_model.joblib'))
    with open(os.path.join(model_dir, 'rf_metadata.json'), 'w') as f:
        json.dump(metadata, f, indent=2)

if __name__ == '__main__':
    run_lomo_evaluation()
    train_production_model()
