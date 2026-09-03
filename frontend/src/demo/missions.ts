export interface Waypoint {
  id: string;
  lat: number;
  lon: number;
}

export interface MissionConfig {
  id: string;
  name: string;
  terrainSource: string;
  waypoints: Waypoint[];
  bounds: {
    lat_min: number;
    lat_max: number;
    lon_min: number;
    lon_max: number;
  };
}

export const missions: Record<string, MissionConfig> = {
  mountain: {
    id: 'mountain',
    name: 'Mountain Mission',
    terrainSource: '/terrain/mountain_heightmap.json',
    waypoints: [
      { id: 'M1', lat: 30.05, lon: 78.05 },
      { id: 'M2', lat: 30.10, lon: 78.12 },
      { id: 'M3', lat: 30.16, lon: 78.20 },
      { id: 'M4', lat: 30.22, lon: 78.28 },
      { id: 'M5', lat: 30.27, lon: 78.34 },
      { id: 'M6', lat: 30.12, lon: 78.38 }
    ],
    bounds: { lat_min: 30.00, lat_max: 30.30, lon_min: 78.00, lon_max: 78.45 }
  },
  desert: {
    id: 'desert',
    name: 'Desert Mission',
    terrainSource: '/terrain/desert_heightmap.json',
    waypoints: [
      { id: 'D1', lat: 26.55, lon: 70.55 },
      { id: 'D2', lat: 26.62, lon: 70.65 },
      { id: 'D3', lat: 26.70, lon: 70.75 },
      { id: 'D4', lat: 26.78, lon: 70.85 },
      { id: 'D5', lat: 26.88, lon: 70.94 },
      { id: 'D6', lat: 26.95, lon: 70.65 }
    ],
    bounds: { lat_min: 26.50, lat_max: 27.00, lon_min: 70.50, lon_max: 71.00 }
  },
  western_ghats: {
    id: 'western_ghats',
    name: 'Western Ghats',
    terrainSource: '/terrain/western_ghats_heightmap.json',
    waypoints: [
      { id: 'W1', lat: 15.05, lon: 73.75 },
      { id: 'W2', lat: 15.12, lon: 73.84 },
      { id: 'W3', lat: 15.20, lon: 73.94 },
      { id: 'W4', lat: 15.28, lon: 74.04 },
      { id: 'W5', lat: 15.38, lon: 74.12 },
      { id: 'W6', lat: 15.45, lon: 73.90 }
    ],
    bounds: { lat_min: 15.00, lat_max: 15.50, lon_min: 73.70, lon_max: 74.20 }
  },
  flat_plain: {
    id: 'flat_plain',
    name: 'Flat Plain',
    terrainSource: '/terrain/flat_plain_heightmap.json',
    waypoints: [
      { id: 'F1', lat: 25.05, lon: 81.55 },
      { id: 'F2', lat: 25.12, lon: 81.65 },
      { id: 'F3', lat: 25.20, lon: 81.75 },
      { id: 'F4', lat: 25.28, lon: 81.85 },
      { id: 'F5', lat: 25.38, lon: 81.94 },
      { id: 'F6', lat: 25.47, lon: 81.70 }
    ],
    bounds: { lat_min: 25.00, lat_max: 25.50, lon_min: 81.50, lon_max: 82.00 }
  }
};
