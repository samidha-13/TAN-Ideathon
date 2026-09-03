import React, { useEffect, useState, useMemo, useRef } from 'react';
import { Play, Pause, RotateCcw, Home, Activity, Target, AlignLeft, Settings, Mountain, ShieldAlert, ChevronRight } from 'lucide-react';
import { missions } from '../demo/missions';
import { generateMissionData } from '../demo/demoReplay';
import Map3D from './Map3D';
import { CesiumMap } from './CesiumMap';

// SVG airplane string for UI
const planeSvgPath = "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z";

export const Dashboard: React.FC = () => {
  const [activeMissionId, setActiveMissionId] = useState('mountain');
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeIndex, setCurrentTimeIndex] = useState(0);
  const [activeTab, setActiveTab] = useState('OVERVIEW');
  const [cesiumCrashed, setCesiumCrashed] = useState(false);

  const mission = missions[activeMissionId];
  const missionData = useMemo(() => generateMissionData(mission.waypoints, 200, 10), [mission]);

  useEffect(() => {
    let interval: number;
    if (isPlaying && currentTimeIndex < missionData.length - 1) {
      interval = window.setInterval(() => {
        setCurrentTimeIndex(t => Math.min(t + 1, missionData.length - 1));
      }, 50); // fast playback
    } else if (currentTimeIndex >= missionData.length - 1) {
      setIsPlaying(false);
    }
    return () => window.clearInterval(interval);
  }, [isPlaying, currentTimeIndex, missionData.length]);

  const state = missionData[currentTimeIndex];

  // Fetch heightmap to render actual real SRTM terrain profile in TAN INFO
  const [heightmap, setHeightmap] = useState<any>(null);
  useEffect(() => {
    fetch(mission.terrainSource)
      .then(r => r.json())
      .then(h => setHeightmap(h))
      .catch(e => console.error(e));
  }, [mission.terrainSource]);

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
  const agl = Math.max(0, state.alt - terrainElev);

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
               {Object.keys(missions).map(k => <option className="bg-slate-900" key={k} value={k}>{missions[k].name.toUpperCase()}</option>)}
             </select>
          </div>
          
          <div className="w-px h-10 bg-[#2a2d36]"></div>

          <div className="flex flex-col gap-1">
             <span className="text-[10px] text-gray-400 tracking-widest">SCENARIO</span>
             <span className="text-[#ef4444] font-bold text-sm tracking-wider">GNSS DENIED</span>
          </div>
          
          <div className="w-px h-10 bg-[#2a2d36]"></div>

          <div className="flex flex-col gap-1">
             <span className="text-[10px] text-gray-400 tracking-widest">UTC</span>
             <span className="font-mono text-white text-sm">08:12:34</span>
          </div>

          <div className="flex flex-col gap-1">
             <span className="text-[10px] text-gray-400 tracking-widest">RUN TIME</span>
             <span className="font-mono text-white text-sm">{Math.floor(state.time / 60).toString().padStart(2, '0')}:{(state.time % 60).toFixed(1).padStart(4, '0')}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={() => setIsPlaying(!isPlaying)} className="hover:bg-gray-800 transition-colors px-4 py-2 rounded-[4px] border border-[#2a2d36] flex items-center gap-2 text-[11px] font-bold tracking-widest text-[#d1d5db]">
            {isPlaying ? <><Pause size={14} /> PAUSE</> : <><Play size={14} /> PLAY</>}
          </button>
          <button onClick={() => { setCurrentTimeIndex(0); setIsPlaying(false); }} className="hover:bg-gray-800 transition-colors px-4 py-2 rounded-[4px] border border-[#2a2d36] flex items-center gap-2 text-[11px] font-bold tracking-widest text-[#d1d5db]">
            <RotateCcw size={14} /> RESET
          </button>
        </div>
      </header>

      {/* 2. Main Flight Displays */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Pilot Forward HUD (55%) */}
        <div className="w-[55%] relative overflow-hidden bg-black shrink-0 border-r border-[#2a2d36]">
          <Map3D mission={mission} data={missionData} currentTimeIndex={currentTimeIndex} mode="hud" />
          
          {/* Overlays on HUD directly mimicking reference */}
          
          {/* Top Heading Tape */}
          <div className="absolute top-4 left-1/2 -translate-x-1/2 flex flex-col items-center z-10 w-80">
            <div className="flex items-center gap-2 text-[11px] font-mono tracking-widest mb-1">
               <span className="text-[#a3e635]">HDG</span>
               <span className="text-white text-lg bg-[#0e161f] border border-gray-700/50 px-2 leading-tight">{state.hdg.toFixed(0)}</span>
               <span className="text-[#a3e635]">MAG</span>
            </div>
            
            <div className="relative w-full h-8 overflow-hidden font-mono text-[10px] text-white">
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[8px] border-transparent border-t-white"></div>
                <div className="flex absolute bottom-0 gap-[36px]" style={{ transform: `translateX(calc(50% - ${state.hdg * 4}px))` }}>
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
                    {state.ias.toFixed(0)}
                    <div className="absolute -right-2 top-1/2 -translate-y-1/2 w-0 h-0 border-y-4 border-y-transparent border-l-[6px] border-l-gray-600"></div>
                 </div>
                 
                 {/* Scale */}
                 <div className="flex-1 border-r-2 border-[#a3e635] relative overflow-hidden flex flex-col justify-center items-end pr-2 text-xs">
                     {/* Pseudo moving ticks (simulated) */}
                     {[-30, -20, -10, 0, 10, 20, 30].map(v => (
                         <div key={v} className="h-8 flex flex-col justify-end items-end relative w-full text-gray-300">
                             {(state.ias + v) > 0 && Math.floor((state.ias + v)/10)*10}
                             <div className="absolute bottom-0 right-[-8px] w-3 h-[2px] bg-[#a3e635]"></div>
                             <div className="absolute bottom-4 right-[-8px] w-2 h-[1px] bg-[#a3e635]"></div>
                         </div>
                     ))}
                 </div>
             </div>
             <div className="text-[#a3e635] text-[10px] mt-2 whitespace-nowrap">GS {state.ias.toFixed(0)} KT</div>
          </div>

          {/* Right ALT Block */}
          <div className="absolute top-20 right-16 bottom-20 w-16 z-10 flex flex-col font-mono text-white select-none">
             <div className="text-center text-[10px] mb-2 leading-none">ALT<br/>FT</div>
             <div className="flex-1 relative flex">
                 {/* Current ALT Box */}
                 <div className="absolute right-[-16px] top-1/2 -translate-y-1/2 bg-black border border-gray-600 px-2 py-1 text-base z-20 w-[68px] text-left">
                    {state.alt.toFixed(0)}
                    <div className="absolute -left-2 top-1/2 -translate-y-1/2 w-0 h-0 border-y-4 border-y-transparent border-r-[6px] border-r-gray-600"></div>
                 </div>
                 
                 {/* Scale */}
                 <div className="flex-1 border-l-2 border-[#a3e635] relative overflow-hidden flex flex-col justify-center items-start pl-2 text-xs">
                     {[-300, -200, -100, 0, 100, 200, 300].map(v => (
                         <div key={v} className="h-8 flex flex-col justify-end items-start relative w-full text-gray-300">
                             {(state.alt + v) > 0 && Math.floor((state.alt + v)/100)*100}
                             <div className="absolute bottom-0 left-[-8px] w-3 h-[2px] bg-[#a3e635]"></div>
                             <div className="absolute bottom-4 left-[-8px] w-2 h-[1px] bg-[#a3e635]"></div>
                         </div>
                     ))}
                 </div>
             </div>
             
             {/* Vertical speed bug mockup outside scale */}
             <div className="absolute top-1/2 -translate-y-1/2 -right-12 bg-[#2a2d36] px-1 text-[10px] border border-gray-600 font-mono">
                 {Math.round(state.vs / 100) * 100}
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
             <div className="absolute top-1 text-[11px] font-mono font-bold text-white bg-black/50 px-1 border border-white/40">{state.hdg.toFixed(0)}°</div>
             <div className="absolute top-0 w-full h-full transform" style={{ transform: `rotate(${-state.hdg}deg)` }}>
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
             {state.gnssStatus === 'DENIED' ? <>GPS<br/>DENIED</> : ''}
          </div>
          <div className="absolute bottom-32 right-32 font-bold font-mono text-sm tracking-wider text-[#d946ef] text-center pointer-events-none drop-shadow-[0_2px_2px_rgba(0,0,0,1)]">
             {state.tanMatchScore > 50 ? <>TERRAIN<br/>MATCHING</> : ''}
          </div>
          
          {/* Nav Mode Box Left Bottom */}
          <div className="absolute bottom-6 left-6 border border-gray-600/50 bg-black/60 p-2 font-mono text-[10px] z-10 rounded-[4px] w-40 text-gray-300 pointer-events-none">
              <div className="mb-2">
                 <div className="text-gray-500 uppercase tracking-widest leading-tight">NAV MODE</div>
                 <div className="text-[#a3e635] text-xs font-bold leading-none">{state.navMode.replace('_', ' ')}</div>
              </div>
              <div className="border-t border-gray-700 pt-1">
                 <div className="text-gray-400 capitalize tracking-wide mb-1">POS UNCERTAINTY (1σ)</div>
                 <div className="flex justify-between text-[#d1d5db]"><span>HORIZ</span> <span>{(state.errorEkf * 0.8).toFixed(1)} m</span></div>
                 <div className="flex justify-between text-[#d1d5db]"><span>VERT</span> <span>{(state.errorEkf * 0.4).toFixed(1)} m</span></div>
              </div>
          </div>

        </div>

        {/* Right: 45% Tactical Mission Map */}
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
          { l: 'HDG', v: `${state.hdg.toFixed(0)}°`, c: 'text-[#4ade80]' },
          { l: 'TRK', v: `${state.trk.toFixed(0)}°`, c: 'text-white' },
          { l: 'IAS', v: `${state.ias.toFixed(0)} KT`, c: 'text-white' },
          { l: 'ALT (MSL)', v: `${state.alt.toFixed(0)} FT`, c: 'text-white' },
          { l: 'AGL', v: `${agl.toFixed(0)} FT`, c: 'text-white' },
          { l: 'VS', v: `${state.vs.toFixed(0)} FPM`, c: 'text-white' },
          { l: 'TURN RATE', v: `${state.turnRate.toFixed(1)} °/s`, c: 'text-white' },
          { l: 'G LOAD', v: `${state.gLoad.toFixed(2)} g`, c: 'text-white' },
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
                    <div className="text-xl text-orange-400">{state.errorEkf.toFixed(1)} <span className="text-xs">meters</span></div>
                    {/* Position Error Graph */}
                    <div className="h-12 w-full bg-slate-900 border border-slate-800 rounded relative">
                       <svg width="100%" height="100%" preserveAspectRatio="none">
                         <polyline 
                           fill="none" 
                           stroke="#f97316" 
                           strokeWidth="2" 
                           points={missionData.slice(0, currentTimeIndex).map((d, i) => `${(i / missionData.length) * 100},${100 - (d.errorEkf / 3)}`).join(' ')}
                         />
                       </svg>
                       <div className="absolute inset-0 border-l border-b border-slate-700 pointer-events-none"></div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <h3 className="text-slate-500 text-[10px] tracking-widest border-b border-slate-800 pb-1">INS DRIFT (DEAD RECKONING)</h3>
                    <div className="text-lg text-fuchsia-500">{state.insDriftM.toFixed(1)} <span className="text-xs">meters</span></div>
                    <p className="text-slate-600 text-[9px] text-justify pr-2 font-mono mt-1 leading-tight">
                      During GNSS denial, INS accumulates temporal drift. 
                    </p>
                  </div>

                  <div className="space-y-4">
                    <h3 className="text-slate-500 text-[10px] tracking-widest border-b border-slate-800 pb-1">CURRENT EKF MODE</h3>
                    <div className="text-lg text-[#4ade80]">{state.navMode.replace('_', ' ')}</div>
                  </div>
              </div>
            )}

            {activeTab === 'SENSORS' && (
              <div className="flex gap-12 font-mono">
                 <div className="w-1/3 space-y-2">
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">GNSS RECEIVER</span>
                      <span className={`text-[10px] font-bold ${state.gnssStatus === 'DENIED' ? 'text-red-500' : 'text-green-500'}`}>{state.gnssStatus}</span>
                   </div>
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">RADAR ALTIMETER</span>
                      <span className={`text-[10px] font-bold ${state.radarStatus === 'FAULT' ? 'text-red-500' : state.radarStatus === 'ISOLATED' ? 'text-orange-500' : 'text-green-500'}`}>{state.radarStatus}</span>
                   </div>
                 </div>
                 <div className="w-1/3 space-y-2">
                   <div className="flex justify-between items-center bg-slate-900 p-2 border border-slate-800">
                      <span className="text-white text-[10px]">INERTIAL (INS)</span>
                      <span className="text-[10px] font-bold text-green-500">ACTIVE</span>
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
                      <div className="text-[10px] text-green-400">{state.terrainObs.toFixed(1)}%</div>
                    </div>
                    <div>
                      <div className="text-[9px] text-slate-500 mb-1 tracking-widest">MATCH SCORE</div>
                      <div className="text-[10px] text-green-400">
                         {state.radarStatus === 'FAULT' || state.radarStatus === 'ISOLATED' || state.tanMatchScore === 0 ? 'N/A' : state.tanMatchScore.toFixed(1)}
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
                 {state.time >= 10 && <div className="flex gap-4"><span className="text-cyan-600">10.0</span> <span className="text-red-500">GNSS SIGNAL DENIED / JAMMED</span></div>}
                 {state.time >= 30 && <div className="flex gap-4"><span className="text-cyan-600">30.0</span> <span className="text-orange-400">INS DRIFT INCREASING</span></div>}
                 {state.time >= 55 && <div className="flex gap-4"><span className="text-cyan-600">55.0</span> <span className="text-blue-400">TERRAIN MATCH SEARCH INITIATED</span></div>}
                 {state.time >= 75 && <div className="flex gap-4"><span className="text-cyan-600">75.0</span> <span className="text-green-400">TAN CORRECTION ACTIVE</span></div>}
                 {state.time >= 120 && <div className="flex gap-4"><span className="text-cyan-600">120.0</span> <span className="text-red-500">RADAR ALTIMETER FAULT</span></div>}
                 {state.time >= 140 && <div className="flex gap-4"><span className="text-cyan-600">140.0</span> <span className="text-orange-400">FDI ISOLATES RADAR</span></div>}
                 {state.time >= 160 && <div className="flex gap-4"><span className="text-cyan-600">160.0</span> <span className="text-green-400">RADAR RECOVERED</span></div>}
                 {state.time >= 180 && <div className="flex gap-4"><span className="text-cyan-600">180.0</span> <span className="text-green-400">TAN+EKF AID RESTORED</span></div>}
              </div>
            )}
            
            {activeTab === 'POSITION ERROR' || activeTab === 'SYSTEM STATUS' || activeTab === 'FDI SUMMARY' ? (
                <div className="font-mono text-[10px] text-gray-500 h-full flex items-center justify-center">
                    Data populating from demoReplay.ts...
                </div>
            ) : null}
          </div>
      </div>
    </div>
  );
};

export default Dashboard;
