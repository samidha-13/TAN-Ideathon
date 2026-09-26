import os
import math

with open('navigation/ekf.py', 'r', encoding='utf-8') as f:
    ekf_code = f.read()

old_predict = '''    def predict(self, dt: float = 0.1) -> None:
        """
        EKF prediction step.
        F ≈ I (error states evolve slowly for straight-and-level flight).
        P ← F P Fᵀ + Q
        """
        # F = Identity for this simplified error-state formulation
        # P ← P + Q  (since F = I, F P Fᵀ = P)
        self._P = _mat_add(self._P, self._Q)
        # Clamp diagonal to prevent runaway
        for i in range(_N):
            self._P[i][i] = min(self._P[i][i], 1e4)'''

new_predict = '''    def predict(self, ins_lat: float = 0.0, dt: float = 0.1) -> None:
        """
        EKF prediction step.
        Couples velocity error to position error.
        """
        F = _mat_eye(_N)
        m_per_deg_lon = self._M_PER_DEG * math.cos(math.radians(ins_lat))
        if m_per_deg_lon < 1.0: m_per_deg_lon = 1.0
        
        F[_I_LAT][_I_VN] = dt / self._M_PER_DEG
        F[_I_LON][_I_VE] = dt / m_per_deg_lon
        F[_I_ALT][_I_VD] = -dt

        # State prediction: x = F * x
        self._x = _mat_vec_mul(F, self._x)
        
        # P = F * P * Fᵀ + Q
        FP = _mat_mul(F, self._P)
        FPFt = _mat_mul(FP, _mat_T(F))
        self._P = _mat_add(FPFt, self._Q)
        
        # Clamp diagonal to prevent runaway
        for i in range(_N):
            self._P[i][i] = min(self._P[i][i], 1e4)'''

ekf_code = ekf_code.replace(old_predict, new_predict)

old_update_gnss = '''        r_deg = r_pos_m / self._M_PER_DEG
        r_alt = r_alt_m

        # H: 3×9, rows select [δ_lat, δ_lon, δ_alt]
        H = _mat_zeros(3, _N)
        H[0][_I_LAT] = 1.0
        H[1][_I_LON] = 1.0
        H[2][_I_ALT] = 1.0

        # Innovation
        z = [
            gnss_lat - ins_lat,
            gnss_lon - ins_lon,
            gnss_alt - ins_alt,
        ]

        # R measurement noise
        R = _mat_zeros(3, 3)
        R[0][0] = r_deg ** 2
        R[1][1] = r_deg ** 2
        R[2][2] = r_alt ** 2'''

new_update_gnss = '''        r_deg_lat = r_pos_m / self._M_PER_DEG
        m_per_deg_lon = self._M_PER_DEG * math.cos(math.radians(ins_lat))
        if m_per_deg_lon < 1.0: m_per_deg_lon = 1.0
        r_deg_lon = r_pos_m / m_per_deg_lon
        r_alt = r_alt_m

        # H: 3×9, rows select [δ_lat, δ_lon, δ_alt]
        H = _mat_zeros(3, _N)
        H[0][_I_LAT] = 1.0
        H[1][_I_LON] = 1.0
        H[2][_I_ALT] = 1.0

        # Innovation
        z = [
            gnss_lat - ins_lat,
            gnss_lon - ins_lon,
            gnss_alt - ins_alt,
        ]

        # R measurement noise
        R = _mat_zeros(3, 3)
        R[0][0] = r_deg_lat ** 2
        R[1][1] = r_deg_lon ** 2
        R[2][2] = r_alt ** 2'''

ekf_code = ekf_code.replace(old_update_gnss, new_update_gnss)

with open('navigation/ekf.py', 'w', encoding='utf-8') as f:
    f.write(ekf_code)

with open('navigation/engine.py', 'r', encoding='utf-8') as f:
    engine_code = f.read()

engine_code = engine_code.replace('self._ekf.predict(dt=dt)', 'self._ekf.predict(ins_lat=ins_state.latitude, dt=dt)')

with open('navigation/engine.py', 'w', encoding='utf-8') as f:
    f.write(engine_code)
