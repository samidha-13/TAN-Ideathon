import React, { useEffect, useState, useMemo } from 'react';
import { Play, Pause, RotateCcw, Home, Activity, Target, AlignLeft, Settings, Mountain, ShieldAlert, ChevronRight } from 'lucide-react';
import { loadMissions, loadNavigationData, type MissionInfo, type NavigationRecord } from '../services/dataService';
import { missions as staticMissions } from '../demo/missions';
import Map3D from './Map3D';
import { CesiumMap } from './CesiumMap';

// SVG airplane string for UI
const planeSvgPath = "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z";

export const Dashboard: React.FC = () => {
  const [missions, setMissions] = useState<MissionInfo[]>([]);
  const [activeMissionId, setActiveMissionId] = useState('mountain_mission');
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTimeIndex, setCurrentTimeIndex] = useState(0);
  const [activeTab, setActiveTab] = useState('OVERVIEW');
  const [, setCesiumCrashed] = useState(false);
  const [missionData, setMissionData] = useState<NavigationRecord[]>([]);
  const [backendError, setBackendError] = useState<string | null>(null);

  useEffect(() => {
    loadMissions()
      .then(m => {
        setMissions(m);
        if (m.length > 0 && !m.find(x => x.id === activeMissionId)) {
          setActiveMissionId(m[0].id);
        }
        setBackendError(null);
      })
      .catch(() => setBackendError('BACKEND OFFLINE'));
  }, []);

  useEffect(() => {
    if (!activeMissionId || backendError) return;
    setMissionData([]);
    setCurrentTimeIndex(0);
    setIsPlaying(false);
    loadNavigationData(activeMissionId)
      .then(data => {
        setMissionData(data);
        setCurrentTimeIndex(0);
        setIsPlaying(false);
        setBackendError(null);
      })
      .catch(() => setBackendError('BACKEND OFFLINE'));
  }, [activeMissionId]);

  useEffect(() => {
    let interval: number;
    if (isPlaying && missionData.length > 0 && currentTimeIndex < missionData.length - 1) {
      interval = window.setInterval(() => {
        setCurrentTimeIndex(t => Math.min(t + 1, missionData.length - 1));
      }, 100 / playbackSpeed); // source records are 10 Hz; speed only changes traversal rate
    } else if (currentTimeIndex >= missionData.length - 1) {
      setIsPlaying(false);
    }
    return () => window.clearInterval(interval);
  }, [isPlaying, currentTimeIndex, missionData.length, playbackSpeed]);

  const state = missionData[currentTimeIndex] || null;
  const configKey = activeMissionId.replace('_mission', '');
  const missionConfig = staticMissions[configKey] || staticMissions['mountain'];

  // Fetch heightmap to render actual real SRTM terrain profile in TAN INFO
  const [heightmap, setHeightmap] = useState<any>(null);
  useEffect(() => {
    if (!missionConfig) return;
    fetch(missionConfig.terrainSource)
      .then(r => r.json())
      .then(h => setHeightmap(h))
      .catch(e => console.error(e));
  }, [missionConfig]);

  let terrainElev = 1500;
  let terrainProfilePts = "";
  if (heightmap) {
      const centerRow = Math.floor(heightmap.resolution / 2);
      const centerCol = Math.floor(heightmap.resolution / 2);
      if (heightmap.data[centerRow] && heightmap.data[centerRow][centerCol]) {
          terrainElev = heightmap.data[centerRow][centerCol];
      }
      const pts = [];
      const res = heightmap.resolution;
      for (let i = 0; i < res; i++) {
         const e = heightmap.data[i][i] || 0; 
         pts.push(`${(i / (res-1)) * 100},${100 - (e/3000)*100}`);
      }
      terrainProfilePts = pts.join(' ');
  }
  const agl = state ? Math.max(0, state.estimated_alt - terrainElev) : 0;
  const MPS_TO_KT = 1.94384;
  const ias = (state?.ground_speed_mps ?? 0) * MPS_TO_KT;
  const vs = (state?.vertical_speed_mps ?? 0) * 196.85; // m/s → ft/min
  const turnRate = state?.turn_rate_dps ?? 0;
  const gLoad = state?.g_load ?? 1.0;
  
  // Backend-generated events (non-empty event field on NavigationRecord)
  const backendEvents = useMemo(() => {
    const seen = new Set<string>();
    return missionData
      .filter(r => r.event && r.event.trim().length > 0)
      .flatMap(r => r.event.split(' | ').map(msg => ({ time: r.timestamp, msg })))
      .filter(e => {
        const key = `${e.time.toFixed(1)}:${e.msg}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }, [missionData]);

  const visibleEvents = useMemo(
    () => backendEvents.filter(e => e.time <= (state?.timestamp ?? 0)),
    [backendEvents, state?.timestamp]
  );
  const missionStart = missionData[0]?.timestamp ?? 0;
  const missionEnd = missionData[missionData.length - 1]?.timestamp ?? missionStart;
  const missionDuration = Math.max(missionEnd - missionStart, 0.001);
  const latestEvent = visibleEvents[visibleEvents.length - 1];
  let hdg = 0;
  if (state && currentTimeIndex > 0) {
     const prev = missionData[currentTimeIndex - 1];
     const dy = state.estimated_lon - prev.estimated_lon;
     const dx = state.estimated_lat - prev.estimated_lat;
     if (dx !== 0 || dy !== 0) {
        hdg = (Math.atan2(dy, dx) * 180 / Math.PI);
        if (hdg < 0) hdg += 360;
     }
  }

  const fdiRadarColor = (status: string) => {
    if (status === 'ISOLATED') return 'text-red-500';
    if (status === 'SUSPECTED') return 'text-orange-500';
    return 'text-green-500';
  };

  if (backendError) {
    return <div className="flex items-center justify-center h-screen bg-black text-red-500 text-2xl font-mono">{backendError}</div>;
  }
  if (!state) {
    return <div className="flex items-center justify-center h-screen bg-black text-white text-xl font-mono">Loading Navigation Data...</div>;
  }

  return (
    <div className="flex flex-col h-screen bg-[#05070a] text-slate-200 overflow-hidden font-sans uppercase">
      {/* 1. Header matching exact Reference */}
      <header className="h-[4.5rem] shrink-0 border-b border-[#2a2d36] bg-[#0c1015] flex items-center justify-between px-6">
        <div className="flex items-center gap-10">
          <div className="flex flex-col justify-center">
            <span className="text-white font-bold tracking-widest text-[16px]">TAN NAVIGATION SYSTEM</span>
            <span className="text-gray-400 text-[10px] tracking-wide mt-1">TERRAIN-AIDED NAVIGATION FOR GNSS-DENIED FLIGHT</span>
          </div>
          
          <div className="w-px h-10 bg-[#2a2d36]"></div>

          <div className="flex flex-col gap-1">
             <span className="text-[10px] text-gray-400 tracking-widest">MISSION</span>
             <select 
               className="bg-transparent text-[#4ade80] font-bold text-sm outline-none cursor-pointer tracking-wider"
               value={activeMissionId}
               onChange={(e) => {
                 setActiveMissionId(e.target.value);
                 setCurrentTimeIndex(0);
                 setIsPlaying(false);
                 setCesiumCrashed(false);
               }}
             >
               {missions.map(m => <option className="bg-slate-900" key={m.id} value={m.id}>{m.name.toUpperCase()}</option>)}
             </select>
          </div>
          
          <div className="w-px h-10 bg-[#2a2d36]"></div>

          <div className="flex flex-col gap-1">
             <span className="text-[10px] text-gray-400 tracking-widest">SCENARIO</span>
             <span className="text-[#ef4444] font-bold text-sm tracking-wider">{state.gnss_accepted ? 'FULL AID' : 'GNSS DENIED'}</span>
          </div>
          
          <div className="w-px h-10 bg-[#2a2d36]"></div>

          <div className="flex flex-col gap-1">
             <span className="text-[10px] text-gray-400 tracking-widest">UTC</span>
             <span className="font-mono text-white text-sm">08:12:34</span>
          </div>

          <div className="flex flex-col gap-1">
             <span className="text-[10px] text-gray-400 tracking-widest">RUN TIME</span>
             <span className="font-mono text-white text-sm">{Math.floor(state.timestamp / 60).toString().padStart(2, '0')}:{(state.timestamp % 60).toFixed(1).padStart(4, '0')}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={() => setIsPlaying(!isPlaying)} className="hover:bg-gray-800 transition-colors px-4 py-2 rounded-[4px] border border-[#2a2d36] flex items-center gap-2 text-[11px] font-bold tracking-widest text-[#d1d5db]">
            {isPlaying ? <><Pause size={14} /> PAUSE</> : <><Play size={14} /> PLAY</>}
          </button>
          <button onClick={() => { setCurrentTimeIndex(0); setIsPlaying(false); }} className="hover:bg-gray-800 transition-colors px-4 py-2 rounded-[4px] border border-[#2a2d36] flex items-center gap-2 text-[11px] font-bold tracking-widest text-[#d1d5db]">
            <RotateCcw size={14} /> RESET
          </button>
          <select aria-label="Playback speed" value={playbackSpeed} onChange={(e) => setPlaybackSpeed(Number(e.target.value))} className="bg-[#0c1015] border border-[#2a2d36] rounded px-2 py-2 text-[11px] font-mono text-[#d1d5db]">
            {[1, 2, 5, 10].map(speed => <option key={speed} value={speed}>{speed}x</option>)}
          </select>
        </div>
      </header>

      <section className="h-14 shrink-0 bg-[#080b0f] border-b border-[#2a2d36] px-6 py-2 font-mono">
        <div className="flex justify-between text-[10px] text-slate-400 mb-1"><span>PLAYBACK TIMELINE</span><span>{state.timestamp.toFixed(1)}s / {missionEnd.toFixed(1)}s {latestEvent ? `— ${latestEvent.msg}` : ''}</span></div>
        <div className="relative h-5">
          <input aria-label="Mission timeline" type="range" min="0" max={Math.max(missionData.length - 1, 0)} value={currentTimeIndex} onChange={(e) => { setCurrentTimeIndex(Number(e.target.value)); setIsPlaying(false); }} className="absolute inset-x-0 top-1 w-full accent-lime-400" />
          {backendEvents.map((event, index) => <button key={`${event.time}-${index}`} title={`${event.time.toFixed(1)}s — ${event.msg}`} onClick={() => { const target = missionData.findIndex(r => r.timestamp >= event.time); if (target >= 0) { setCurrentTimeIndex(target); setIsPlaying(false); } }} className="absolute top-0 z-10 h-4 w-1 bg-orange-400 hover:bg-white" style={{ left: `${((event.time - missionStart) / missionDuration) * 100}%` }} />)}
        </div>
      </section>

      {/* 2. Main Flight Displays */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Pilot Forward HUD (55%) */}
        <div className="w-[55%] relative overflow-hidden bg-black shrink-0 border-r border-[#2a2d36]">
          <Map3D mission={missionConfig} data={missionData} currentTimeIndex={currentTimeIndex} mode="hud" />
          
          {/* Overlays on HUD directly mimicking reference */}
          
          {/* Top Heading Tape */}
          <div className="absolute top-4 left-1/2 -translate-x-1/2 flex flex-col items-center z-10 w-80">
            <div className="flex items-center gap-2 text-[11px] font-mono tracking-widest mb-1">
               <span className="text-[#a3e635]">HDG</span>
               <span className="text-white text-lg bg-[#0e161f] border border-gray-700/50 px-2 leading-tight">{hdg.toFixed(0)}</span>
               <span className="text-[#a3e635]">MAG</span>
            </div>
            
            <div className="relative w-full h-8 overflow-hidden font-mono text-[10px] text-white">
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[8px] border-transparent border-t-white"></div>
                <div className="flex absolute bottom-0 gap-[36px]" style={{ transform: `translateX(calc(50% - ${hdg * 4}px))` }}>
                  {Array.from({length: 72}).map((_, i) => (
                      <div key={i} className="flex flex-col items-center w-[4px] shrink-0">
                          {i%3===0 ? <span className="mb-px">{i * 10}</span> : <div className="h-1"></div>}
                          <div className={`w-[1px] bg-white ${i%3===0 ? 'h-3' : 'h-1.5'}`}></div>
                      </div>
                  ))}
                </div>
                <div className="absolute bottom-0 w-full h-[1px] bg-white/50"></div>
            </div>
          </div>

          {/* Left IAS Block */}
          <div className="absolute top-20 left-16 bottom-20 w-16 z-10 flex flex-col font-mono text-white select-none">
             <div className="text-center text-[10px] mb-2 leading-none">IAS<br/>KT</div>
             <div className="flex-1 relative flex">
                 {/* Current IAS Box overlaid on center */}
                 <div className="absolute left-[-16px] top-1/2 -translate-y-1/2 bg-black border border-gray-600 px-2 py-1 text-base z-20 w-[60px] text-right">
                    {ias.toFixed(0)}
                    <div className="absolute -right-2 top-1/2 -translate-y-1/2 w-0 h-0 border-y-4 border-y-transparent border-l-[6px] border-l-gray-600"></div>
                 </div>
                 
                 {/* Scale */}
                 <div className="flex-1 border-r-2 border-[#a3e635] relative overflow-hidden flex flex-col justify-center items-end pr-2 text-xs">
                     {/* Pseudo moving ticks (simulated) */}
                     {[-30, -20, -10, 0, 10, 20, 30].map(v => (
                         <div key={v} className="h-8 flex flex-col justify-end items-end relative w-full text-gray-300">
                             {(ias + v) > 0 && Math.floor((ias + v)/10)*10}
                             <div className="absolute bottom-0 right-[-8px] w-3 h-[2px] bg-[#a3e635]"></div>
                             <div className="absolute bottom-4 right-[-8px] w-2 h-[1px] bg-[#a3e635]"></div>
                         </div>
                     ))}
                 </div>
             </div>
             <div className="text-[#a3e635] text-[10px] mt-2 whitespace-nowrap">GS {ias.toFixed(0)} KT</div>
          </div>

          {/* Right ALT Block */}
          <div className="absolute top-20 right-16 bottom-20 w-16 z-10 flex flex-col font-mono text-white select-none">
             <div className="text-center text-[10px] mb-2 leading-none">ALT<br/>FT</div>
             <div className="flex-1 relative flex">
                 {/* Current ALT Box */}
                 <div className="absolute right-[-16px] top-1/2 -translate-y-1/2 bg-black border border-gray-600 px-2 py-1 text-base z-20 w-[68px] text-left">
                    {state.estimated_alt.toFixed(0)}
                    <div className="absolute -left-2 top-1/2 -translate-y-1/2 w-0 h-0 border-y-4 border-y-transparent border-r-[6px] border-r-gray-600"></div>
                 </div>
                 
                 {/* Scale */}
                 <div className="flex-1 border-l-2 border-[#a3e635] relative overflow-hidden flex flex-col justify-center items-start pl-2 text-xs">
                     {[-300, -200, -100, 0, 100, 200, 300].map(v => (
                         <div key={v} className="h-8 flex flex-col justify-end items-start relative w-full text-gray-300">
                             {(state.estimated_alt + v) > 0 && Math.floor((state.estimated_alt + v)/100)*100}
                             <div className="absolute bottom-0 left-[-8px] w-3 h-[2px] bg-[#a3e635]"></div>
                             <div className="absolute bottom-4 left-[-8px] w-2 h-[1px] bg-[#a3e635]"></div>
                         </div>
                     ))}
                 </div>
             </div>
             
             {/* Vertical speed bug mockup outside scale */}
             <div className="absolute top-1/2 -translate-y-1/2 -right-12 bg-[#2a2d36] px-1 text-[10px] border border-gray-600 font-mono">
                 {vs.toFixed(0)}
             </div>

             <div className="text-[#a3e635] text-[10px] mt-2 whitespace-nowrap text-right pr-2">AGL {agl.toFixed(0)} FT</div>
          </div>
          
          {/* Pitch Ladder & Flight Director Center */}
          <div className="absolute top-0 bottom-32 left-0 right-0 pointer-events-none flex flex-col items-center justify-center opacity-90 z-10">
             <div className="w-96 relative flex flex-col items-center justify-center">
                 {/* 10 deg up */}
                 <div className="flex justify-between w-48 mb-8 text-[11px] font-mono text-white items-end border-b-2 border-x-2 border-white/70 h-2"><span>10</span><span>10</span></div>
                 
                 {/* 5 deg up */}
                 <div className="flex justify-between w-32 mb-8 text-[11px] font-mono text-white items-end border-b-2 border-x-2 border-white/70 h-2"><span>5</span><span>5</span></div>
                 
                 {/* Center Aircraft Symbol (Yellow Chevron) */}
                 <div className="w-full flex items-center justify-center relative mb-8">
                     <div className="w-16 h-1 bg-yellow-400"></div>
                     <div className="w-8 h-8 rounded-full border-2 border-yellow-400 absolute"></div>
                     <div className="w-2 h-2 bg-yellow-400 absolute"></div>
                     <div className="w-16 h-1 bg-yellow-400 absolute right-[calc(50%+24px)]"></div>
                     <div className="w-16 h-1 bg-yellow-400 absolute left-[calc(50%+24px)]"></div>
                     
                     <div className="absolute w-[80%] h-px bg-yellow-400/40 opacity-50 z-[-1]"></div>
                 </div>

                 {/* 5 deg down */}
                 <div className="flex justify-between w-32 mb-8 text-[11px] font-mono text-white items-start border-t-2 border-x-2 border-white/70 h-2"><span>5</span><span>5</span></div>
                 
                 {/* 10 deg down */}
                 <div className="flex justify-between w-48 text-[11px] font-mono text-white items-start border-t-2 border-x-2 border-white/70 h-2"><span>10</span><span>10</span></div>
             </div>
          </div>
          
          {/* Compass Rose (Bottom Center) */}
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-40 h-40 rounded-full border-2 border-white/50 bg-[#080d12]/30 flex items-center justify-center z-10 pointer-events-none">
             <div className="absolute top-1 text-[11px] font-mono font-bold text-white bg-black/50 px-1 border border-white/40">{hdg.toFixed(0)}°</div>
             <div className="absolute top-0 w-full h-full transform" style={{ transform: `rotate(${-hdg}deg)` }}>
                 {/* Mock ticks */}
                 <div className="absolute top-2 w-full text-center text-xs text-white font-mono">N</div>
                 <div className="absolute bottom-2 w-full text-center text-xs text-white font-mono transform rotate-180">S</div>
                 <div className="absolute left-2 top-1/2 -translate-y-1/2 text-xs text-white font-mono transform -rotate-90">W</div>
                 <div className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-white font-mono transform rotate-90">E</div>
                 
                 <svg width="100%" height="100%" viewBox="0 0 100 100" className="absolute inset-0">
                    {[...Array(36)].map((_,i) => (
                        <line key={i} x1="50" y1="10" x2="50" y2={i%9===0 ? "15" : "13"} stroke="white" strokeWidth="1" transform={`rotate(${i*10} 50 50)`} opacity="0.6"/>
                    ))}
                 </svg>
             </div>
          </div>

          {/* HUD Warnings/Status */}
          <div className="absolute bottom-32 left-32 font-bold font-mono text-sm tracking-wider text-[#d946ef] text-center pointer-events-none drop-shadow-[0_2px_2px_rgba(0,0,0,1)]">
             {!state.gnss_accepted ? <>GPS<br/>DENIED</> : ''}
          </div>
          <div className="absolute bottom-32 right-32 font-bold font-mono text-sm tracking-wider text-[#d946ef] text-center pointer-events-none drop-shadow-[0_2px_2px_rgba(0,0,0,1)]">
             {state.tan_valid ? <>TERRAIN<br/>MATCHING</> : ''}
          </div>
          
          {/* Nav Mode Box Left Bottom */}
          <div className="absolute bottom-6 left-6 border border-gray-600/50 bg-black/60 p-2 font-mono text-[10px] z-10 rounded-[4px] w-40 text-gray-300 pointer-events-none">
              <div className="mb-2">
                 <div className="text-gray-500 uppercase tracking-widest leading-tight">NAV MODE</div>
                 <div className="text-[#a3e635] text-xs font-bold leading-none">{state.nav_mode.replace('_', ' ')}</div>
              </div>
              <div className="border-t border-gray-700 pt-1">
                 <div className="text-gray-400 capitalize tracking-wide mb-1">POS UNCERTAINTY (1σ)</div>
                 <div className="flex justify-between text-[#d1d5db]"><span>HORIZ</span> <span>{Math.sqrt(state.uncertainty_lat_m**2 + state.uncertainty_lon_m**2).toFixed(1)} m</span></div>
                 <div className="flex justify-between text-[#d1d5db]"><span>VERT</span> <span>{state.uncertainty_alt_m.toFixed(1)} m</span></div>
              </div>
          </div>

        </div>

        <div className="flex-1 w-[45%] relative bg-[#0c1015] shrink-0 border-l px-[4px] py-[4px] border-[#2a2d36] overflow-hidden">
             <CesiumMap 
                data={missionData} 
                currentTimeIndex={currentTimeIndex} 
                onError={() => {}} 
             />

          {/* Tactical Display Legend upper left */}
          <div className="absolute top-4 left-4 z-10 pointer-events-none">
             <div className="bg-[#05070a]/80 backdrop-blur border border-[#2a2d36] p-4 rounded-[4px] text-[10px] font-mono shrink-0">
                 <div className="flex items-center gap-3 mb-2 text-white">
                     <span className="w-6 border-t-[2px] border-dashed border-white"></span> REFERENCE PATH (TRUTH)
                 </div>
                 <div className="flex items-center gap-3 mb-2 text-white">
                     <span className="w-6 border-t-[2px] border-dashed border-[#d946ef]"></span> INS (DEAD RECKONING)
                 </div>
                 <div className="flex items-center gap-3 mb-3 text-white">
                     <span className="w-6 border-t-[2px] border-solid border-[#4ade80]"></span> TAN + EKF (ESTIMATED)
                 </div>
                 <div className="flex items-center gap-3 text-white">
                     <div className="w-6 flex items-center justify-center">
                         <svg width="12" height="12" viewBox="0 0 24 24" fill="white"><path d={planeSvgPath}/></svg>
                     </div>
                     AIRCRAFT POSITION
                 </div>
             </div>
          </div>
          
          {/* North Target top right */}
          <div className="absolute top-4 right-4 z-10 pointer-events-none">
             <div className="w-12 h-12 bg-[#05070a]/70 rounded-full border border-[#2a2d36] flex flex-col items-center justify-start py-1">
                 <span className="text-[12px] font-bold text-white font-mono leading-none">N</span>
                 <svg width="16" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2"><path d="M12 21V3M12 3l-5 5M12 3l5 5"/></svg>
             </div>
          </div>
          
          {/* Map Controls Mockup top right below N */}
          <div className="absolute top-20 right-4 z-10 flex flex-col gap-2 font-mono text-[9px] text-[#9ca3af] pointer-events-none">
             <div className="bg-[#05070a]/70 border border-[#2a2d36] w-10 flex flex-col rounded-[2px] overflow-hidden">
                 <div className="h-8 flex items-center justify-center border-b border-[#2a2d36] text-xl">+</div>
                 <div className="h-8 flex items-center justify-center text-xl">-</div>
             </div>
             <div className="bg-[#05070a]/70 border border-[#2a2d36] w-10 h-8 rounded-[2px] flex items-center justify-center">3D</div>
             <div className="bg-[#05070a]/70 border border-[#2a2d36] w-10 h-10 rounded-[2px] flex items-center justify-center tracking-wider text-center pt-1 leading-none">TERRAIN</div>
          </div>

          <div className="absolute bottom-6 right-20 z-10 pointer-events-none">
             <div className="flex items-end text-[10px] font-mono text-white mb-1 justify-center block text-center">
                 <span>5 NM</span>
             </div>
             <div className="w-32 border-b border-x border-white/80 h-2"></div>
          </div>
        </div>
      </div>

      {/* 3. Bottom Flight Strip */}
      <div className="h-16 shrink-0 bg-[#080b0f] flex border-y border-[#2a2d36] items-center justify-between px-16 divide-x divide-[#2a2d36]">
        {[
          { l: 'HDG', v: `${hdg.toFixed(0)}°`, c: 'text-[#4ade80]' },
          { l: 'TRK', v: `${hdg.toFixed(0)}°`, c: 'text-white' },
          { l: 'IAS', v: `${ias.toFixed(0)} KT`, c: 'text-white' },
          { l: 'ALT (MSL)', v: `${state.estimated_alt.toFixed(0)} FT`, c: 'text-white' },
          { l: 'AGL', v: `${agl.toFixed(0)} FT`, c: 'text-white' },
          { l: 'VS', v: `${vs.toFixed(0)} FPM`, c: 'text-white' },
          { l: 'TURN RATE', v: `${turnRate.toFixed(1)} °/s`, c: 'text-white' },
          { l: 'G LOAD', v: `${gLoad.toFixed(2)} g`, c: 'text-white' },
        ].map((i, idx) => (
          <div key={idx} className="flex flex-col items-center flex-1">
             <span className="text-[10px] text-gray-400 tracking-widest mb-1">{i.l}</span>
             <span className={`text-[17px] font-mono ${i.c}`}>{i.v}</span>
          </div>
        ))}
      </div>

      {/* 4. Bottom Tabs Area matching reference explicitly */}
      <div className="h-48 shrink-0 bg-[#0c1015] flex flex-col border-t border-[#2a2d36]">
          {/* TABS HEADER */}
          <div className="h-10 flex border-b border-[#2a2d36] shrink-0">
            {[
              { id: 'OVERVIEW', icon: <Home size={14}/> },
              { id: 'SENSORS', icon: <Activity size={14}/> },
              { id: 'POSITION ERROR', icon: <Target size={14}/> },
              { id: 'EVENT LOG', icon: <AlignLeft size={14}/> },
              { id: 'SYSTEM STATUS', icon: <Settings size={14}/> },
              { id: 'TAN / TERRAIN INFO', icon: <Mountain size={14}/> },
              { id: 'FDI SUMMARY', icon: <ShieldAlert size={14}/> },
              { id: 'ML DETAILS', icon: <Activity size={14}/> },
            ].map((tab, idx) => (
              <button 
                key={idx}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 flex gap-2 items-center justify-center text-[10px] font-mono tracking-widest border-r border-[#2a2d36] transition-colors
                            ${activeTab === tab.id ? 'bg-[#18212f] text-white border-t-[2px] border-t-[#3b82f6]' : 'text-gray-400 hover:bg-[#111721] border-t-[2px] border-t-transparent'}`}
              >
                {tab.icon} {tab.id}
              </button>
            ))}
            <button className="px-4 border-r border-[#2a2d36] flex items-center justify-center text-gray-500 hover:text-white">
               <ChevronRight size={16} />
            </button>
          </div>
          
          {/* TAB CONTENT (RESERVED 15-20% HEIGHT CONTINUING EXISTING WORKFLOW) */}
          <div className="flex-1 p-4 overflow-y-auto w-full max-w-full">
            {activeTab === 'OVERVIEW' && (
              <div className="grid grid-cols-4 gap-6 h-full font-mono text-sm">
                  <div className="space-y-4 col-span-2">
                    <h3 className="text-slate-500 text-[10px] tracking-widest border-b border-slate-800 pb-1">3D POSITION ERROR</h3>
                    <div className="text-xl text-orange-400">{state.error_3d_m.toFixed(1)} <span className="text-xs">meters</span></div>
                    {/* Position Error Graph */}
                    <div className="h-12 w-full bg-slate-900 border border-slate-800 rounded relative">
                       <svg width="100%" height="100%" preserveAspectRatio="none">
                         <polyline 
                           fill="none" 
                           stroke="#f97316" 
                           strokeWidth="2" 
                           points={missionData.slice(0, currentTimeIndex).map((d, i) => `${(i / missionData.length) * 100},${100 - (d.error_3d_m / 3)}`).join(' ')}
                         />
                       </svg>
                       <div className="absolute inset-0 border-l border-b border-slate-700 pointer-events-none"></div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <h3 className="text-slate-500 text-[10px] tracking-widest border-b border-slate-800 pb-1">INS DRIFT (DEAD RECKONING)</h3>
                    <div className="text-lg text-fuchsia-500">{state.ins_drift_m.toFixed(1)} <span className="text-xs">meters</span></div>
                    <p className="text-slate-600 text-[9px] text-justify pr-2 font-mono mt-1 leading-tight">
                      During GNSS denial, INS accumulates temporal drift. 
                    </p>
                  </div>

                  <div className="space-y-4">
                    <h3 className="text-slate-500 text-[10px] tracking-widest border-b border-slate-800 pb-1">CURRENT EKF MODE</h3>
                    <div className="text-lg text-[#4ade80]">{state.nav_mode.replace('_', ' ')}</div>
                  </div>
              </div>
            )}

            {activeTab === 'SENSORS' && (
              <div className="flex gap-12 font-mono">
                 <div className="w-1/3 space-y-2">
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">GNSS RECEIVER</span>
                      <span className={`text-[10px] font-bold ${!state.gnss_accepted ? 'text-red-500' : 'text-green-500'}`}>{state.gnss_accepted ? 'AVAILABLE' : 'DENIED'}</span>
                   </div>
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">RADAR ALTIMETER</span>
                      <span className={`text-[10px] font-bold ${fdiRadarColor(state.fdi_radar)}`}>{state.fdi_radar || 'ACCEPTED'}</span>
                   </div>
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">MAGNETOMETER</span>
                      <span className={`text-[10px] font-bold ${fdiRadarColor(state.fdi_mag)}`}>{state.fdi_mag || 'ACCEPTED'}</span>
                   </div>
                 </div>
                 <div className="w-1/3 space-y-2">
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">INERTIAL (INS)</span>
                      <span className="text-[10px] font-bold text-green-500">ACTIVE</span>
                   </div>
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">MAGNAV AID</span>
                      <span className={`text-[10px] font-bold ${state.magnav_available ? 'text-green-500' : 'text-slate-500'}`}>{state.magnav_available ? state.magnav_quality : 'UNAVAILABLE'}</span>
                   </div>
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">ML ANOMALY MONITOR</span>
                      <span className={`text-[10px] font-bold ${state.ml_status === 'ANOMALOUS' ? 'text-orange-400' : state.ml_status === 'NORMAL' ? 'text-green-500' : 'text-slate-500'}`}>{state.ml_status || 'UNAVAILABLE'} {state.ml_score === null ? '' : `(${state.ml_score.toFixed(3)})`}</span>
                   </div>
                 </div>
              </div>
            )}

            {activeTab === 'TAN / TERRAIN INFO' && (
              <div className="flex flex-col h-full font-mono">
                 <div className="grid grid-cols-4 gap-6">
                    <div>
                      <div className="text-[9px] text-slate-500 mb-1 tracking-widest">TERRAIN SOURCE</div>
                      <div className="text-[10px] text-blue-300">SRTM 1-ARC SEC</div>
                    </div>
                    <div>
                      <div className="text-[9px] text-slate-500 mb-1 tracking-widest">OBSERVABILITY</div>
                      <div className="text-[10px] text-green-400">{state.terrain_obs}</div>
                    </div>
                    <div>
                      <div className="text-[9px] text-slate-500 mb-1 tracking-widest">MATCH SCORE</div>
                      <div className="text-[10px] text-green-400">
                         {!state.radar_accepted || state.fdi_radar === 'ISOLATED' || state.fdi_radar === 'SUSPECTED'
                           ? 'N/A'
                           : state.tan_match_score.toFixed(3)}
                      </div>
                    </div>
                 </div>
                 <div className="flex-1 mt-2">
                    <h3 className="text-slate-500 text-[9px] tracking-widest border-b border-slate-800 pb-1 mb-1">TERRAIN PROFILE (ACTUAL SRTM)</h3>
                    <div className="h-12 w-128 bg-slate-900 border border-slate-800 rounded relative overflow-hidden">
                       <svg width="100%" height="100%" preserveAspectRatio="none">
                         {terrainProfilePts && (
                             <>
                               {/* Fill underneath */}
                               <polygon fill="rgba(34, 51, 34, 0.5)" points={`0,100 ${terrainProfilePts} 100,100`} />
                               <polyline fill="none" stroke="#22c55e" strokeWidth="2" points={terrainProfilePts} />
                             </>
                         )}
                       </svg>
                    </div>
                 </div>
              </div>
            )}

            {activeTab === 'EVENT LOG' && (
              <div className="font-mono text-[10px] space-y-1 overflow-y-auto">
                 <div className="flex gap-4 opacity-50"><span className="text-cyan-600">00.0</span> <span className="text-slate-400">MISSION START</span></div>
                 {visibleEvents.map((e, i) => (
                   <div key={i} className="flex gap-4">
                     <span className="text-cyan-600">{e.time.toFixed(1).padStart(5, '0')}</span>
                     <span className={
                       e.msg.includes('DENIED') || e.msg.includes('ISOLATED') ? 'text-red-500' :
                       e.msg.includes('ANOMALY') || e.msg.includes('DEGRADED') || e.msg.includes('LOW') ? 'text-orange-400' :
                       e.msg.includes('TAN') || e.msg.includes('RESTORED') ? 'text-green-400' :
                       'text-slate-400'
                     }>{e.msg}</span>
                   </div>
                 ))}
                 {visibleEvents.length === 0 && (
                   <div className="text-gray-500 italic">No events yet — playback will reveal backend-generated events.</div>
                 )}
              </div>
            )}
            
            {activeTab === 'FDI SUMMARY' && (
                <div className="font-mono text-[10px] grid grid-cols-3 gap-6">
                  {[
                    { label: 'GNSS', status: state.fdi_gnss, accepted: state.gnss_accepted },
                    { label: 'RADAR', status: state.fdi_radar, accepted: state.radar_accepted },
                    { label: 'MAGNETOMETER', status: state.fdi_mag, accepted: state.mag_accepted },
                  ].map(s => (
                    <div key={s.label} className="bg-slate-900 p-3 border border-slate-800">
                      <div className="text-slate-500 mb-1">{s.label}</div>
                      <div className={`font-bold ${s.status === 'ISOLATED' ? 'text-red-500' : s.status === 'SUSPECTED' ? 'text-orange-500' : 'text-green-500'}`}>
                        {s.status}
                      </div>
                      <div className="text-slate-400 mt-1">{s.accepted ? 'USED BY EKF' : 'EXCLUDED'}</div>
                    </div>
                  ))}
                </div>
            )}

            {activeTab === 'ML DETAILS' && (
              <div className="font-mono text-[10px] grid grid-cols-3 gap-6">
                <div className="space-y-1"><div className="text-slate-500">ML ANOMALY MONITOR · ISOLATION FOREST</div><div className={state.ml_status === 'ANOMALOUS' ? 'text-orange-400 font-bold' : 'text-green-500 font-bold'}>{state.ml_status}</div><div>DECISION SCORE: {state.ml_score === null ? 'N/A' : state.ml_score.toFixed(4)}</div><div className="text-slate-500">ADVISORY ONLY — DOES NOT OVERRIDE DETERMINISTIC FDI OR EKF.</div></div>
                <div className="space-y-1"><div className="text-slate-500">OFFLINE EVALUATION</div><div>ISOLATION FOREST · UNSUPERVISED · 13 FEATURES</div><div>12,476 HEALTHY TRAINING SAMPLES · 14,076 EVALUATION SAMPLES</div><div>PRECISION 35.26% · RECALL 51.13% · F1 41.73% · ACCURACY 83.77%</div></div>
                <div className="space-y-1"><div className="text-slate-500">ML PATH</div><div>NAVIGATION RECORD ↓ FEATURE ENGINEERING ↓ 13 FEATURES ↓ ISOLATION FOREST ↓ ANOMALY SCORE ↓ ML STATUS</div><div className="text-slate-500">ML DOES NOT MODIFY FDI, TAN, OR EKF.</div></div>
              </div>
            )}

            {activeTab === 'POSITION ERROR' || activeTab === 'SYSTEM STATUS' ? (
                <div className="font-mono text-[10px] text-gray-500 h-full flex items-center justify-center">
                    Data sourced from FastAPI navigation engine...
                </div>
            ) : null}
          </div>
      </div>
    </div>
  );
};

export default Dashboard;
