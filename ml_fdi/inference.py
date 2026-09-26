import os
import numpy as np
import joblib
from tensorflow.keras.models import load_model

CLASS_MAP = ['HEALTHY', 'GNSS_FAULT', 'RADAR_FAULT', 'MAGNETOMETER_FAULT', 'COMBINED_FAULT']

class FDIWatchdog:
    def __init__(self, model_path=None, scaler_path=None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if model_path is None:
            model_path = os.path.join(base_dir, 'models', 'lstm_optimized_final.keras')
        if scaler_path is None:
            scaler_path = os.path.join(base_dir, 'models', 'lstm_sequence_scaler.pkl')
            
        self.model = load_model(model_path)
        self.scaler = joblib.load(scaler_path)
        
    def predict(self, raw_sequence_2d):
        """
        raw_sequence_2d: numpy array of shape (50, 9)
        Features must be strictly ordered:
        [
            'gnss_residual_lat', 'gnss_residual_lon', 'gnss_residual_alt', 
            'gnss_residual_3d_m', 'delta_gnss_residual_3d_m',
            'radar_residual_agl', 'delta_radar_residual_agl',
            'mag_total_field', 'delta_mag_total_field'
        ]
        """
        # 1. Scale the sequence
        scaled_seq = self.scaler.transform(raw_sequence_2d)
        
        # 2. Reshape to batch format (1, 50, 9)
        input_tensor = np.expand_dims(scaled_seq, axis=0)
        
        # 3. Predict
        probs = self.model.predict(input_tensor, verbose=0)[0]
        
        # 4. Format Output
        pred_idx = int(np.argmax(probs))
        
        return {
            "predicted_class": CLASS_MAP[pred_idx],
            "confidence": float(probs[pred_idx]),
            "probabilities": {CLASS_MAP[i]: float(probs[i]) for i in range(5)}
        }
