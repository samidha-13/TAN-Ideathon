export interface NavigationRecord {
  timestamp: number;
  mission_index: number;
  estimated_lat: number;
  estimated_lon: number;
  estimated_alt: number;
  ins_lat: number;
  ins_lon: number;
  ins_alt: number;
  nav_mode: string;
  gnss_accepted: boolean;
  radar_accepted: boolean;
  mag_accepted: boolean;
  tan_valid: boolean;
  tan_match_score: number;
  tan_residual_m: number;
  terrain_obs: string;
  magnav_available: boolean;
  magnav_quality: string;
  uncertainty_lat_m: number;
  uncertainty_lon_m: number;
  uncertainty_alt_m: number;
  fdi_radar: string;
  fdi_gnss: string;
  fdi_mag: string;
  truth_lat: number;
  truth_lon: number;
  error_lat_m: number;
  error_lon_m: number;
  error_3d_m: number;
  ins_drift_m: number;
  ground_speed_mps: number;
  vertical_speed_mps: number;
  turn_rate_dps: number;
  g_load: number;
  event: string;
  ml_status: string;
  ml_score: number | null;
}

export interface MissionInfo {
  id: string;
  name: string;
}

const API_BASE = 'http://localhost:8000/api';

export const loadMissions = async (): Promise<MissionInfo[]> => {
  try {
    const response = await fetch(`${API_BASE}/missions`);
    if (!response.ok) throw new Error('Backend Offline');
    return await response.json();
  } catch (error) {
    throw new Error('BACKEND OFFLINE');
  }
};

export const loadNavigationData = async (missionId: string): Promise<NavigationRecord[]> => {
  try {
    const response = await fetch(`${API_BASE}/navigation/${missionId}/state`);
    if (!response.ok) throw new Error('Navigation data unavailable');
    return await response.json();
  } catch (error) {
    throw new Error('BACKEND OFFLINE');
  }
};
