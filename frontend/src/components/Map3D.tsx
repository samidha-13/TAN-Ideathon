import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Line } from '@react-three/drei';
import * as THREE from 'three';
import type { DroneState } from '../demo/demoReplay';
import type { MissionConfig } from '../demo/missions';

interface Map3DProps {
  mission: MissionConfig;
  data: DroneState[];
  currentTimeIndex: number;
  mode: 'hud' | 'map';
}

interface Heightmap {
  resolution: number;
  data: number[][]; // [lat_idx][lon_idx]
  min_elevation: number;
  max_elevation: number;
  bounds: {
    lat_min: number;
    lat_max: number;
    lon_min: number;
    lon_max: number;
  };
}

const TerrainMesh: React.FC<{ heightmap: Heightmap, centerLat: number }> = ({ heightmap, centerLat }) => {
  const geometry = useMemo(() => {
    const latMeters = (heightmap.bounds.lat_max - heightmap.bounds.lat_min) * 111000;
    const lonMeters = (heightmap.bounds.lon_max - heightmap.bounds.lon_min) * 111000 * Math.cos(centerLat * Math.PI / 180);
    const { resolution, data, min_elevation, max_elevation } = heightmap;
    
    const geom = new THREE.PlaneGeometry(lonMeters, latMeters, resolution - 1, resolution - 1);
    const pos = geom.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    
    // Topographic color palette
    const cLow = new THREE.Color("#162113");     // Dark deep valleys
    const cMid = new THREE.Color("#373f22");     // Olive mountain slopes
    const cHigh = new THREE.Color("#5e584a");    // Dry rocky ridges
    const cPeak = new THREE.Color("#827a6b");    // High altitude stone
    const c = new THREE.Color();
    
    for (let i = 0; i < pos.count; i++) {
        const row = Math.floor(i / resolution);
        const col = i % resolution;
        if (data[row] && data[row][col] !== undefined) {
             const elev = data[row][col];
             pos.setZ(i, Math.max(0, elev) * 1.5);
             
             // Map color using actual elevation normalized 
             const n = Math.max(0, Math.min(1, (elev - min_elevation) / (max_elevation - min_elevation)));
             if (n < 0.3) c.lerpColors(cLow, cMid, n / 0.3);
             else if (n < 0.7) c.lerpColors(cMid, cHigh, (n - 0.3) / 0.4);
             else c.lerpColors(cHigh, cPeak, (n - 0.7) / 0.3);
             
             colors[i * 3] = c.r;
             colors[i * 3 + 1] = c.g;
             colors[i * 3 + 2] = c.b;
        }
    }
    
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geom.computeVertexNormals();
    geom.computeBoundingBox();
    geom.computeBoundingSphere();
    
    return geom;
  }, [heightmap, centerLat]);

  return (
    <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]}>
      <meshStandardMaterial 
        vertexColors={true}
        roughness={0.9}
        metalness={0.1}
        flatShading={false}
      />
    </mesh>
  );
};

const Aircraft = ({ state, mode, centerLat, centerLon }: { state: DroneState, mode: string, centerLat: number, centerLon: number }) => {
  const { camera } = useThree();
  
  const x = (state.ekfLon - centerLon) * 111000 * Math.cos(centerLat * Math.PI / 180);
  const z = -(state.ekfLat - centerLat) * 111000;
  const y = state.alt;
  const pos = new THREE.Vector3(x, y, z);
  
  useFrame(() => {
    if (mode === 'hud') {
      const hdgRad = -(state.hdg - 90) * (Math.PI / 180);
      
      // Tight cockpit trailing camera
      const camOffset = new THREE.Vector3(
        -Math.cos(hdgRad) * 40,
        30,     // Only 30m above aircraft center 
        Math.sin(hdgRad) * 40
      );
      
      const targetOffset = new THREE.Vector3(
        Math.cos(hdgRad) * 4000,
        -300,  // Look slightly downwards into the valleys
        -Math.sin(hdgRad) * 4000
      );
      
      camera.position.lerp(pos.clone().add(camOffset), 0.5);
      camera.lookAt(pos.clone().add(targetOffset));
    } else {
        // High oblique tactical camera for right panel
        camera.position.x += (x - camera.position.x) * 0.1;
        camera.position.z += (z + 8000 - camera.position.z) * 0.1;
        camera.position.y += (12000 - camera.position.y) * 0.1;
        camera.lookAt(x, y - 2000, z); 
    }
  });

  return mode === 'map' ? (
    <mesh position={pos}>
      <sphereGeometry args={[40, 8, 8]} />
      <meshBasicMaterial color="#ffffff" />
    </mesh>
  ) : null;
};

const FlightPaths = ({ data, currentTimeIndex, centerLat, centerLon }: { data: DroneState[], currentTimeIndex: number, centerLat: number, centerLon: number }) => {
    const history = data.slice(0, currentTimeIndex + 1);
    const lonScale = 111000 * Math.cos(centerLat * Math.PI / 180);
    const latScale = -111000;

    const mkPoints = (keyLat: 'refLat'|'insLat'|'ekfLat', keyLon: 'refLon'|'insLon'|'ekfLon') => 
        history.map(d => new THREE.Vector3((d[keyLon] - centerLon) * lonScale, d.alt, (d[keyLat] - centerLat) * latScale));

    const refPts = mkPoints('refLat', 'refLon');
    const insPts = mkPoints('insLat', 'insLon');
    const ekfPts = mkPoints('ekfLat', 'ekfLon');
    
    return (
        <group position={[0, 40, 0]}> {/* Bump slightly to avoid z-fighting with terrain peaks */}
            {refPts.length > 1 && <Line points={refPts} color="white" dashed dashSize={400} gapSize={200} lineWidth={2} />}
            {insPts.length > 1 && <Line points={insPts} color="#ff00ff" lineWidth={2} dashed dashSize={300} gapSize={150} />}
            {ekfPts.length > 1 && <Line points={ekfPts} color="#00ff00" lineWidth={3} />}
        </group>
    );
};

export const Map3D: React.FC<Map3DProps> = ({ mission, data, currentTimeIndex, mode }) => {
  const [heightmap, setHeightmap] = useState<Heightmap | null>(null);

  const centerLat = (mission.bounds.lat_min + mission.bounds.lat_max) / 2;
  const centerLon = (mission.bounds.lon_min + mission.bounds.lon_max) / 2;

  useEffect(() => {
    fetch(mission.terrainSource)
      .then(r => r.json())
      .then(h => setHeightmap(h))
      .catch(e => console.error(e));
  }, [mission.terrainSource]);

  const currentState = data[currentTimeIndex];

  return (
    <Canvas camera={{ position: [0, 5000, 5000], far: 100000, fov: mode === 'hud' ? 65 : 45 }}>
      {mode === 'hud' ? (
        <>
          <color attach="background" args={['#17223b']} />
          <fog attach="fog" args={['#17223b', 2000, 40000]} />
        </>
      ) : (
        <color attach="background" args={['#080c14']} />
      )}
      
      {mode === 'map' && <OrbitControls enableRotate={false} />}
      
      <ambientLight intensity={0.4} />
      <hemisphereLight skyColor="#2e4d73" groundColor="#0f1710" intensity={0.5} />
      <directionalLight position={[15000, 10000, 8000]} intensity={1.2} color="#ffeed6" />
      <directionalLight position={[-10000, 8000, -8000]} intensity={0.3} color="#9bb4d6" />
      
      {heightmap && <TerrainMesh heightmap={heightmap} centerLat={centerLat} />}
      
      {currentState && mode === 'map' && <FlightPaths data={data} currentTimeIndex={currentTimeIndex} centerLat={centerLat} centerLon={centerLon} />}
      {currentState && <Aircraft state={currentState} mode={mode} centerLat={centerLat} centerLon={centerLon} />}
    </Canvas>
  );
};

export default Map3D;
