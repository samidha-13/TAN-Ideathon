import type { Waypoint } from './missions';

export interface DroneState {
  time: number;
  lat: number;
  lon: number;
  alt: number; // Aircraft altitude
  hdg: number;
  trk: number;
  ias: number;
  vs: number;
  turnRate: number;
  gLoad: number;
  navMode: string;
  gnssStatus: 'AVAILABLE' | 'DENIED';
  radarStatus: 'ACTIVE' | 'FAULT' | 'ISOLATED' | 'RECOVERED';
  insDriftM: number;
  tanMatchScore: number;
  terrainObs: number;
  fdiGnss: 'ACCEPTED' | 'ISOLATED';
  fdiRadar: 'ACCEPTED' | 'SUSPECTED' | 'ISOLATED';
  fdiMag: 'ACCEPTED';
  
  // Simulated paths
  refLat: number;
  refLon: number;
  insLat: number;
  insLon: number;
  ekfLat: number;
  ekfLon: number;
  
  errorEkf: number;
}

export function generateMissionData(waypoints: Waypoint[], durationSec: number = 200, fps: number = 10): DroneState[] {
  const data: DroneState[] = [];
  const totalFrames = durationSec * fps;
  
  // For simplicity, interpolate linearly across waypoints for the full duration
  const wpCount = waypoints.length;
  
  for (let i = 0; i <= totalFrames; i++) {
    const t = i / fps;
    
    // 1. Progress along route
    const progress = t / durationSec; 
    const wpIndex = Math.min(Math.floor(progress * (wpCount - 1)), wpCount - 2);
    const wpProg = (progress * (wpCount - 1)) - wpIndex;
    
    const wpA = waypoints[wpIndex];
    const wpB = waypoints[wpIndex + 1] || wpA;
    
    const refLat = wpA.lat + (wpB.lat - wpA.lat) * wpProg;
    const refLon = wpA.lon + (wpB.lon - wpA.lon) * wpProg;
    
    // Altitude oscillating slightly around 5000 demo alt
    const alt = 5000 + Math.sin(t * 0.1) * 50; 
    const hdg = Math.atan2(wpB.lon - wpA.lon, wpB.lat - wpA.lat) * (180 / Math.PI);
    
    let gnssStatus: 'AVAILABLE' | 'DENIED' = 'AVAILABLE';
    let navMode = 'FULL_AID';
    let fdiGnss: 'ACCEPTED' | 'ISOLATED' = 'ACCEPTED';
    let radarStatus: 'ACTIVE' | 'FAULT' | 'ISOLATED' | 'RECOVERED' = 'ACTIVE';
    let fdiRadar: 'ACCEPTED' | 'SUSPECTED' | 'ISOLATED' = 'ACCEPTED';
    
    let insDrift = 0;
    let errorEkf = 0;
    
    // INS Drift logic
    if (t >= 10 && t < 180) {
      gnssStatus = 'DENIED';
      fdiGnss = 'ISOLATED';
      navMode = 'INS_ONLY';
      
      const driftT = t - 10;
      insDrift = 0.5 * (driftT * driftT);
    }
    
    let tanMatchScore = 0;
    let terrainObs = 0;
    
    if (t >= 55) {
      terrainObs = 40 + Math.sin(t) * 10;
    }
    
    if (t >= 55 && t < 75) {
      tanMatchScore = ((t - 55) / 20) * 80; 
    }
    
    let ekfOffsetRatio = 1.0; 
    
    if (t >= 75 && t < 120) { 
      navMode = 'TAN_AID';
      tanMatchScore = 80 + Math.random() * 5; 
      
      ekfOffsetRatio = 1.0 - ((t - 75) / 25);
      if (ekfOffsetRatio < 0.1) ekfOffsetRatio = 0.1;
    }
    
    if (t >= 100 && t < 120) {
      ekfOffsetRatio = 0.1;
    }
    
    if (t >= 120 && t < 160) {
      radarStatus = 'FAULT';
      fdiRadar = t >= 140 ? 'ISOLATED' : 'SUSPECTED';
      navMode = 'INS_ONLY';
      ekfOffsetRatio = 0.1 + ((t - 120) / 40) * 0.5;
    }
    
    if (t >= 160 && t < 180) {
      radarStatus = 'RECOVERED';
      fdiRadar = 'ACCEPTED';
      navMode = 'TAN_AID';
      ekfOffsetRatio = 0.6 - ((t - 160) / 20) * 0.5;
    }
    
    if (t >= 180) {
      gnssStatus = 'AVAILABLE';
      fdiGnss = 'ACCEPTED';
      navMode = 'FULL_AID';
      ekfOffsetRatio = 0.05;
      insDrift = insDrift * 0.9; 
    }
    
    const maxDriftLat = (insDrift / 111000) * Math.sin(t * 0.05); 
    const maxDriftLon = (insDrift / 111000) * Math.cos(t * 0.05);
    
    const insLat = refLat + maxDriftLat;
    const insLon = refLon + maxDriftLon;
    
    const ekfLat = refLat + maxDriftLat * ekfOffsetRatio;
    const ekfLon = refLon + maxDriftLon * ekfOffsetRatio;
    
    errorEkf = Math.sqrt(Math.pow((ekfLat-refLat)*111000, 2) + Math.pow((ekfLon-refLon)*111000, 2));

    data.push({
      time: t,
      lat: ekfLat,
      lon: ekfLon,
      alt,
      hdg,
      trk: hdg + 1.5, 
      ias: 350 + Math.sin(t)*10,
      vs: Math.cos(t * 0.1) * 200,
      turnRate: 0,
      gLoad: 1.0,
      navMode,
      gnssStatus,
      radarStatus,
      insDriftM: insDrift,
      tanMatchScore,
      terrainObs,
      fdiGnss,
      fdiRadar,
      fdiMag: 'ACCEPTED',
      refLat,
      refLon,
      insLat,
      insLon,
      ekfLat,
      ekfLon,
      errorEkf
    });
  }
  
  return data;
}
