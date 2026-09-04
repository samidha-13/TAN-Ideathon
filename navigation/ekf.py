"""
Extended Kalman Filter (EKF) for terrain-aided navigation.

State vector (9-element)
------------------------
  x[0]  δ_lat    latitude  error   (degrees)
  x[1]  δ_lon    longitude error   (degrees)
  x[2]  δ_alt    altitude  error   (metres)
  x[3]  δ_vn     north velocity error (m/s)
  x[4]  δ_ve     east  velocity error (m/s)
  x[5]  δ_vd     down  velocity error (m/s)
  x[6]  δ_roll   roll  error (rad)
  x[7]  δ_pitch  pitch error (rad)
  x[8]  δ_yaw    yaw   error (rad)

Prediction step
---------------
The INS propagates the full state.  The EKF state error vector is driven by
process noise only (INS mechanisation errors are modelled as process noise).
F ≈ I (linear time-invariant error model for a slowly evolving aircraft).

Update step (per aiding source)
-------------------------------
Each valid measurement produces an observation z = H x + noise.

GNSS position
  H_gnss[:, 0] = 1  (δ_lat),  H_gnss[:, 1] = 1  (δ_lon),  H_gnss[:, 2] = 1  (δ_alt)
  Noise R_gnss: diagonal (σ_lat², σ_lon², σ_alt²)

TAN position
  H_tan[:, 0]  = 1  (δ_lat),  H_tan[:, 1]  = 1  (δ_lon)
  Noise R_tan: diagonal (σ_tan², σ_tan²), σ_tan proportional to match score

Radar AGL (residual cross-check only — used indirectly through TAN)
  Not a direct EKF measurement; TAN handles it.

Only measurements that pass FDI are supplied to the update step.

The EKF NEVER receives ground-truth latitude or longitude.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# State size
_N = 9
# Indices
_I_LAT, _I_LON, _I_ALT = 0, 1, 2
_I_VN,  _I_VE,  _I_VD  = 3, 4, 5
_I_ROLL, _I_PITCH, _I_YAW = 6, 7, 8

# ── tiny matrix library (pure Python, no numpy dependency) ─────────────────

def _mat_zeros(r: int, c: int) -> List[List[float]]:
    return [[0.0] * c for _ in range(r)]

def _mat_eye(n: int) -> List[List[float]]:
    m = _mat_zeros(n, n)
    for i in range(n):
        m[i][i] = 1.0
    return m

def _mat_add(A, B):
    return [[A[i][j] + B[i][j] for j in range(len(A[0]))] for i in range(len(A))]

def _mat_sub(A, B):
    return [[A[i][j] - B[i][j] for j in range(len(A[0]))] for i in range(len(A))]

def _mat_mul(A, B):
    ra, ca = len(A), len(A[0])
    cb = len(B[0])
    C = _mat_zeros(ra, cb)
    for i in range(ra):
        for j in range(cb):
            s = 0.0
            for k in range(ca):
                s += A[i][k] * B[k][j]
            C[i][j] = s
    return C

def _mat_T(A):
    return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]

def _mat_scale(A, s):
    return [[A[i][j] * s for j in range(len(A[0]))] for i in range(len(A))]

def _mat_inv_2x2(A):
    a, b, c, d = A[0][0], A[0][1], A[1][0], A[1][1]
    det = a * d - b * c
    if abs(det) < 1e-30:
        raise ValueError(f"Singular 2×2 matrix (det={det})")
    inv_det = 1.0 / det
    return [[d * inv_det, -b * inv_det], [-c * inv_det, a * inv_det]]

def _mat_inv_3x3(A):
    """Inverse of a 3×3 matrix (Cramer's rule)."""
    a = A
    det = (a[0][0] * (a[1][1]*a[2][2] - a[1][2]*a[2][1])
         - a[0][1] * (a[1][0]*a[2][2] - a[1][2]*a[2][0])
         + a[0][2] * (a[1][0]*a[2][1] - a[1][1]*a[2][0]))
    if abs(det) < 1e-30:
        raise ValueError(f"Singular 3×3 matrix (det={det})")
    inv = _mat_zeros(3, 3)
    inv[0][0] =  (a[1][1]*a[2][2] - a[1][2]*a[2][1]) / det
    inv[0][1] = -(a[0][1]*a[2][2] - a[0][2]*a[2][1]) / det
    inv[0][2] =  (a[0][1]*a[1][2] - a[0][2]*a[1][1]) / det
    inv[1][0] = -(a[1][0]*a[2][2] - a[1][2]*a[2][0]) / det
    inv[1][1] =  (a[0][0]*a[2][2] - a[0][2]*a[2][0]) / det
    inv[1][2] = -(a[0][0]*a[1][2] - a[0][2]*a[1][0]) / det
    inv[2][0] =  (a[1][0]*a[2][1] - a[1][1]*a[2][0]) / det
    inv[2][1] = -(a[0][0]*a[2][1] - a[0][1]*a[2][0]) / det
    inv[2][2] =  (a[0][0]*a[1][1] - a[0][1]*a[1][0]) / det
    return inv

def _vec_sub(a, b):
    return [a[i] - b[i] for i in range(len(a))]

def _mat_vec_mul(A, v):
    return [sum(A[i][j] * v[j] for j in range(len(v))) for i in range(len(A))]


# ── EKF ───────────────────────────────────────────────────────────────────────

@dataclass
class EKFResult:
    """Output of one EKF step."""
    timestamp:        float
    mission_index:    int
    estimated_lat:    float
    estimated_lon:    float
    estimated_alt:    float
    nav_mode:         str            # "FULL_AID", "TAN_ONLY", "GNSS_ONLY", "INS_ONLY"
    gnss_accepted:    bool
    tan_accepted:     bool
    mag_accepted:     bool
    uncertainty_lat:  float          # 1-sigma (degrees)
    uncertainty_lon:  float          # 1-sigma (degrees)
    uncertainty_alt:  float          # 1-sigma (metres)
    fdi_status:       Dict[str, str] = field(default_factory=dict)


class NavigationEKF:
    """
    9-state EKF fusing INS prediction with TAN, GNSS, and MagNav corrections.

    Process noise and measurement noise are expressed in the error-state space.
    The INS mechanisation provides the nominal trajectory; the EKF estimates
    and corrects the error.

    Parameters
    ----------
    q_pos_deg    : position process noise std-dev (degrees/step)
    q_vel        : velocity process noise std-dev (m/s/step)
    q_att        : attitude process noise std-dev (rad/step)
    r_gnss_m     : GNSS position noise std-dev (metres)
    r_tan_m      : TAN position noise std-dev (metres) — adjusted by match score
    """

    _M_PER_DEG = 111_320.0   # rough metres per degree (mid-latitude)

    def __init__(
        self,
        q_pos_deg: float = 1e-6,
        q_vel:     float = 0.05,
        q_att:     float = 1e-4,
        r_gnss_m:  float = 5.0,
        r_tan_m:   float = 200.0,
    ) -> None:
        # State error vector (all zeros = INS is the truth proxy initially)
        self._x: List[float] = [0.0] * _N

        # Covariance (uncertainty) matrix
        # Initialise with moderate uncertainty
        self._P = _mat_eye(_N)
        for i in range(_N):
            # pos: ~1km, vel: ~10 m/s, att: ~0.1 rad
            if i < 3:
                self._P[i][i] = (1e-3) ** 2    # 0.001° ≈ 111 m
            elif i < 6:
                self._P[i][i] = 1.0 ** 2       # 1 m/s
            else:
                self._P[i][i] = (1e-2) ** 2    # ~0.01 rad

        # Process noise covariance Q
        self._Q = _mat_zeros(_N, _N)
        for i in range(3):
            self._Q[i][i]   = q_pos_deg ** 2
        for i in range(3, 6):
            self._Q[i][i]   = q_vel ** 2
        for i in range(6, 9):
            self._Q[i][i]   = q_att ** 2

        # Measurement noise
        self._r_gnss_deg = r_gnss_m / self._M_PER_DEG
        self._r_tan_deg  = r_tan_m  / self._M_PER_DEG

    # ── public interface ──────────────────────────────────────────────────────

    def predict(self, dt: float = 0.1) -> None:
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
            self._P[i][i] = min(self._P[i][i], 1e4)

    def update_gnss(
        self,
        ins_lat: float, ins_lon: float, ins_alt: float,
        gnss_lat: float, gnss_lon: float, gnss_alt: float,
        r_pos_m: float = 5.0,
        r_alt_m: float = 10.0,
    ) -> None:
        """
        EKF update with GNSS position measurement.
        Innovation: z = [gnss_lat − ins_lat, gnss_lon − ins_lon, gnss_alt − ins_alt]
        """
        r_deg = r_pos_m / self._M_PER_DEG
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
        R[2][2] = r_alt ** 2

        self._update(H, z, R, meas_name="GNSS")

    def update_tan(
        self,
        ins_lat: float, ins_lon: float,
        tan_lat: float, tan_lon: float,
        match_score: float = 0.5,
        base_r_m:    float = 300.0,
    ) -> None:
        """
        EKF update with TAN position measurement.
        Noise is inversely scaled by match score: better match → smaller noise.
        """
        # Scale noise: worse match → larger uncertainty
        scale = max(1.0 / (match_score + 0.01), 1.0)
        r_m   = base_r_m * scale
        r_deg = r_m / self._M_PER_DEG

        H = _mat_zeros(2, _N)
        H[0][_I_LAT] = 1.0
        H[1][_I_LON] = 1.0

        z = [
            tan_lat - ins_lat,
            tan_lon - ins_lon,
        ]

        R = _mat_zeros(2, 2)
        R[0][0] = r_deg ** 2
        R[1][1] = r_deg ** 2

        self._update(H, z, R, meas_name="TAN")

    def update_magnav(
        self,
        ins_lat: float, ins_lon: float,
        mag_lat: float, mag_lon: float,
        r_m: float = 500.0,
    ) -> None:
        """
        EKF update with MagNav position estimate.
        Uses same 2D position update form as TAN.
        """
        r_deg = r_m / self._M_PER_DEG

        H = _mat_zeros(2, _N)
        H[0][_I_LAT] = 1.0
        H[1][_I_LON] = 1.0

        z = [
            mag_lat - ins_lat,
            mag_lon - ins_lon,
        ]

        R = _mat_zeros(2, 2)
        R[0][0] = r_deg ** 2
        R[1][1] = r_deg ** 2

        self._update(H, z, R, meas_name="MagNav")

    def get_correction(self) -> List[float]:
        """Return the current error-state vector x."""
        return list(self._x)

    def get_covariance_diagonal(self) -> List[float]:
        """Return the diagonal of P (variances)."""
        return [self._P[i][i] for i in range(_N)]

    def position_uncertainty_1sigma(self) -> tuple:
        """Return (σ_lat_deg, σ_lon_deg, σ_alt_m) 1-sigma uncertainties."""
        cov = self.get_covariance_diagonal()
        return (
            math.sqrt(max(cov[_I_LAT], 0.0)),
            math.sqrt(max(cov[_I_LON], 0.0)),
            math.sqrt(max(cov[_I_ALT], 0.0)),
        )

    def apply_correction_to_ins(self, ins_lat, ins_lon, ins_alt):
        """
        Apply the EKF error-state correction to the INS position estimate.
        After application, reset the error state to zero (closed-loop form).

        Returns corrected (lat, lon, alt).
        """
        corr_lat = ins_lat + self._x[_I_LAT]
        corr_lon = ins_lon + self._x[_I_LON]
        corr_alt = ins_alt + self._x[_I_ALT]
        # Reset error state
        self._x = [0.0] * _N
        return corr_lat, corr_lon, corr_alt

    # ── internal update step ──────────────────────────────────────────────────

    def _update(
        self,
        H:         List[List[float]],
        z:         List[float],
        R:         List[List[float]],
        meas_name: str = "",
    ) -> None:
        """
        Standard EKF update:
            K = P Hᵀ (H P Hᵀ + R)⁻¹
            x = x + K z
            P = (I − K H) P
        """
        m = len(z)  # measurement dimension
        Ht = _mat_T(H)
        PH = _mat_mul(self._P, Ht)         # N×m
        HPH = _mat_mul(H, PH)              # m×m
        S = _mat_add(HPH, R)               # innovation covariance

        try:
            if m == 2:
                S_inv = _mat_inv_2x2(S)
            elif m == 3:
                S_inv = _mat_inv_3x3(S)
            else:
                raise ValueError(f"Unsupported measurement dim {m}")
        except ValueError as e:
            logger.warning("EKF update (%s): %s — skipping update", meas_name, e)
            return

        K = _mat_mul(PH, S_inv)            # N×m (Kalman gain)

        # State update: x ← x + K z
        Kz = _mat_vec_mul(K, z)
        self._x = [self._x[i] + Kz[i] for i in range(_N)]

        # Covariance update: P ← (I − KH) P
        KH = _mat_mul(K, H)               # N×N
        IKH = _mat_sub(_mat_eye(_N), KH)
        self._P = _mat_mul(IKH, self._P)

        # Symmetrise P to prevent drift
        for i in range(_N):
            for j in range(_N):
                avg = (self._P[i][j] + self._P[j][i]) / 2.0
                self._P[i][j] = avg
                self._P[j][i] = avg

        logger.debug(
            "EKF update (%s): inno=%s  δpos=(%.6f°, %.6f°)",
            meas_name,
            [f"{zi:.4f}" for zi in z],
            self._x[_I_LAT],
            self._x[_I_LON],
        )
