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
  activeAid: string;
}

export function generateMissionData(waypoints: Waypoint[], durationSec: number = 200, fps: number = 10, missionId: string = 'mountain'): DroneState[] {
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
    let navMode = 'GNSS AID';
    let fdiGnss: 'ACCEPTED' | 'ISOLATED' = 'ACCEPTED';
    let radarStatus: 'ACTIVE' | 'FAULT' | 'ISOLATED' | 'RECOVERED' = 'ACTIVE';
    let fdiRadar: 'ACCEPTED' | 'SUSPECTED' | 'ISOLATED' = 'ACCEPTED';
    let activeAid = 'NONE';

    
    let insDrift = 0;
    let errorEkf = 0;
    
    // INS Drift logic
    if (t >= 10) {
      if (t < 180) {
        gnssStatus = 'DENIED';
        fdiGnss = 'ISOLATED';
        navMode = 'INS ONLY';
        
        const driftT = t - 10;
        insDrift = 0.5 * (driftT * driftT);
      } else {
        const maxDrift = 0.5 * (170 * 170);
        const recoverT = t - 180;
        insDrift = maxDrift * Math.exp(-recoverT * 0.02);
      }
    }
    
    // Mission-dependent base metrics
    let baseObs = 40;
    let baseMatch = 80;
    let minErr = 0.1;
    if (missionId === 'flat_plain') { baseObs = 2; baseMatch = 10; minErr = 0.7; }
    else if (missionId === 'desert') { baseObs = 15; baseMatch = 30; minErr = 0.4; }
    else if (missionId === 'western_ghats') { baseObs = 30; baseMatch = 60; minErr = 0.2; }
    
    let tanMatchScore = 0;
    let terrainObs = 0;
    
    if (t >= 55) {
      terrainObs = baseObs + Math.sin(t) * (baseObs * 0.1);
    }
    
    if (t >= 55 && t < 75) {
      navMode = 'TAN SEARCHING';
      tanMatchScore = ((t - 55) / 20) * baseMatch; 
    }
    
    let ekfOffsetRatio = 1.0; 
    
    if (t >= 75 && t < 120) { 
      navMode = 'TAN AID';
      activeAid = 'TAN';
      tanMatchScore = baseMatch + Math.random() * 5; 
      
      ekfOffsetRatio = 1.0 - ((t - 75) / 25) * (1.0 - minErr);
      if (ekfOffsetRatio < minErr) ekfOffsetRatio = minErr;
    }
    
    if (t >= 100 && t < 120) {
      ekfOffsetRatio = minErr;
    }
    
    // RADAR FAULT / MAGNAV FAILOVER
    if (t >= 120) {
      radarStatus = 'FAULT';
      fdiRadar = t >= 140 ? 'ISOLATED' : 'SUSPECTED';
      
      if (t < 145) {
        navMode = 'INS ONLY / EVALUATING AIDS';
        activeAid = 'NONE / DEGRADED';
        ekfOffsetRatio = minErr + ((t - 120) / 25) * 0.3; // Diverging away from white
      } else if (t < 150) {
        navMode = 'MAGNAV EVALUATING';
        activeAid = 'NONE / DEGRADED';
        ekfOffsetRatio = minErr + 0.3 + ((t - 145) / 5) * 0.2; // Still diverging
      } else if (t < 155) {
        navMode = 'MAGNAV ACQUIRED';
        activeAid = 'MAGNAV';
        
        // MagNav binds the error
        const peakErr = minErr + 0.5; // reaches this peak at 150
        const magnavPull = Math.min(((t - 150) / 5) * 0.2, 0.2); // Pull back by 0.2
        ekfOffsetRatio = peakErr - magnavPull; // smooth convergence toward white
      } else {
        navMode = 'MAGNAV AID';
        activeAid = 'MAGNAV';
        ekfOffsetRatio = minErr + 0.3; // Stabilized and continues using MagNav
      }
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
      errorEkf,
      activeAid
    });
  }
  
  return data;
}
