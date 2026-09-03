import Papa from 'papaparse';

export interface TrajectoryData {
  mission_index: number;
  timestamp: number;
  latitude: number;
  longitude: number;
  altitude: number;
  velocity_n: number;
  velocity_e: number;
  velocity_d: number;
  roll: number;
  pitch: number;
  yaw: number;
}

export interface GNSSData {
  timestamp: number;
  status: string;
  latitude: number;
  longitude: number;
  altitude: number;
  velocity_n: number;
  velocity_e: number;
  velocity_d: number;
}

export interface FaultsData {
  [timestamp: string]: {
    GNSS: string;
    Radar: string;
    Magnetometer: string;
  };
}

export const loadTrajectoryData = async (missionName: string): Promise<TrajectoryData[]> => {
  const response = await fetch(`/data/missions/${missionName}/trajectory.csv`);
  const text = await response.text();
  return new Promise((resolve) => {
    Papa.parse(text, {
      header: true,
      dynamicTyping: true,
      complete: (results) => {
        resolve(results.data as TrajectoryData[]);
      },
    });
  });
};

export const loadGNSSData = async (missionName: string): Promise<GNSSData[]> => {
  const response = await fetch(`/data/missions/${missionName}/gnss.csv`);
  const text = await response.text();
  return new Promise((resolve) => {
    Papa.parse(text, {
      header: true,
      dynamicTyping: true,
      complete: (results) => {
        resolve(results.data as GNSSData[]);
      },
    });
  });
};

export const loadFaultsData = async (missionName: string): Promise<FaultsData> => {
  const response = await fetch(`/data/missions/${missionName}/faults.json`);
  const json = await response.json();
  return json as FaultsData;
};
