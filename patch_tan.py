import os
import math

with open('navigation/tan.py', 'r', encoding='utf-8') as f:
    tan_code = f.read()

old_compute = '''    def compute(
        self,
        ins_lat:     float,
        ins_lon:     float,
        ins_alt:     float,
        profile:     List[ProfileSample],
        obs_result:  Optional[TerrainObservabilityResult] = None,
    ) -> TANResult:'''

new_compute = '''    def compute(
        self,
        ins_lat:     float,
        ins_lon:     float,
        ins_alt:     float,
        profile:     List[ProfileSample],
        obs_result:  Optional[TerrainObservabilityResult] = None,
        search_radius_m: Optional[float] = None,
    ) -> TANResult:'''
tan_code = tan_code.replace(old_compute, new_compute)

old_logic = '''        # ── 1. Terrain observability ──────────────────────────────────────────
        if obs_result is None:
            elevs, spacing = sample_elevation_profile_around(
                self._terrain, ins_lat, ins_lon,
                radius_m=self._radius, n_points=self._grid_steps,
            )
            obs_result = compute_observability(elevs, spacing)

        if obs_result.level == ObservabilityLevel.LOW:
            return self._reject(
                "terrain observability LOW; TAN measurement rejected",
                obs=obs_result,
            )

        min_ncc = (
            _MIN_NCC_MEDIUM
            if obs_result.level == ObservabilityLevel.MEDIUM
            else _MIN_NCC_HIGH
        )

        # ── 2. Candidate grid around current INS ─────────────────────────────
        candidates = self._build_grid(ins_lat, ins_lon)'''

new_logic = '''        # ── 1. Terrain observability ──────────────────────────────────────────
        radius = search_radius_m if search_radius_m is not None else self._radius
        # Bound radius between 50m and self._radius
        radius = max(50.0, min(radius, self._radius))

        if obs_result is None:
            elevs, spacing = sample_elevation_profile_around(
                self._terrain, ins_lat, ins_lon,
                radius_m=radius, n_points=self._grid_steps,
            )
            obs_result = compute_observability(elevs, spacing)

        if obs_result.level == ObservabilityLevel.LOW:
            min_ncc = 0.90
        elif obs_result.level == ObservabilityLevel.MEDIUM:
            min_ncc = _MIN_NCC_MEDIUM
        else:
            min_ncc = _MIN_NCC_HIGH

        # ── 2. Candidate grid around current INS ─────────────────────────────
        candidates = self._build_grid_dynamic(ins_lat, ins_lon, radius)'''

tan_code = tan_code.replace(old_logic, new_logic)

old_grid = '''    def _build_grid(
        self, centre_lat: float, centre_lon: float
    ) -> List[Tuple[float, float]]:
        m_per_deg_lat = math.pi / 180.0 * self._R
        m_per_deg_lon = math.pi / 180.0 * self._R * math.cos(
            math.radians(centre_lat)
        )
        if m_per_deg_lat == 0 or m_per_deg_lon == 0:
            return []

        step = (2 * self._radius) / (self._grid_steps - 1) if self._grid_steps > 1 else self._radius
        half = self._radius'''

new_grid = '''    def _build_grid_dynamic(
        self, centre_lat: float, centre_lon: float, radius: float
    ) -> List[Tuple[float, float]]:
        m_per_deg_lat = math.pi / 180.0 * self._R
        m_per_deg_lon = math.pi / 180.0 * self._R * math.cos(
            math.radians(centre_lat)
        )
        if m_per_deg_lat == 0 or m_per_deg_lon == 0:
            return []

        step = (2 * radius) / (self._grid_steps - 1) if self._grid_steps > 1 else radius
        half = radius'''
tan_code = tan_code.replace(old_grid, new_grid)

old_return = '''        return TANResult(
            valid           = True,
            estimated_lat   = best_lat,
            estimated_lon   = best_lon,
            match_score     = match_score,
            residual_m      = best_resid,
            search_radius_m = self._radius,
            n_candidates    = len(candidates),
            terrain_obs     = obs_result,
        )'''
new_return = '''        return TANResult(
            valid           = True,
            estimated_lat   = best_lat,
            estimated_lon   = best_lon,
            match_score     = match_score,
            residual_m      = best_resid,
            search_radius_m = radius,
            n_candidates    = len(candidates),
            terrain_obs     = obs_result,
        )'''
tan_code = tan_code.replace(old_return, new_return)

with open('navigation/tan.py', 'w', encoding='utf-8') as f:
    f.write(tan_code)

with open('navigation/engine.py', 'r', encoding='utf-8') as f:
    engine_code = f.read()

# Replace the TAN call in engine.py
old_tan_call = '''                tan_result = self._tan.compute(
                    ins_state.latitude,
                    ins_state.longitude,
                    ins_state.altitude,
                    self._radar_buffer,
                    obs_result=None, # Recomputed inside TAN
                )'''
new_tan_call = '''                tan_unc_radius = 3.0 * max(unc_lat_m, unc_lon_m) + 50.0
                tan_result = self._tan.compute(
                    ins_state.latitude,
                    ins_state.longitude,
                    ins_state.altitude,
                    self._radar_buffer,
                    obs_result=None,
                    search_radius_m=tan_unc_radius,
                )'''

engine_code = engine_code.replace(old_tan_call, new_tan_call)
with open('navigation/engine.py', 'w', encoding='utf-8') as f:
    f.write(engine_code)
