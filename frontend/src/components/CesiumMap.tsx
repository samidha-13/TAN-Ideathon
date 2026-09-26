import React, { useEffect, useRef, useState } from 'react';
import * as Cesium from 'cesium';
import type { NavigationRecord } from '../services/dataService';

// We must import the styling for Cesium
import 'cesium/Build/Cesium/Widgets/widgets.css';

interface CesiumMapProps {
  data: NavigationRecord[];
  currentTimeIndex: number;
  onError: () => void;
}

const planeSvgPath = "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z";
// Explicit SVG dimensions to prevent Cesium rendering a 100% bounds black box over the surface
const svgIconURI = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="white" stroke="black" stroke-width="0.5"><path d="${planeSvgPath}"/></svg>`);

export const CesiumMap: React.FC<CesiumMapProps> = ({ data, currentTimeIndex, onError }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);
  
  // Entity refs for paths and aircraft
  const refPathRef = useRef<Cesium.Entity | null>(null);
  const insPathRef = useRef<Cesium.Entity | null>(null);
  const ekfPathRef = useRef<Cesium.Entity | null>(null);
  const aircraftRef = useRef<Cesium.Entity | null>(null);

  const [hasError, setHasError] = useState(false);

  const currentTimeIndexRef = useRef(currentTimeIndex);
  useEffect(() => {
    currentTimeIndexRef.current = currentTimeIndex;
  }, [currentTimeIndex]);

  useEffect(() => {
    const token = import.meta.env.VITE_CESIUM_ION_TOKEN;
    if (token && token !== 'YOUR_TOKEN_HERE') {
      Cesium.Ion.defaultAccessToken = token;
    }

    if (!containerRef.current || viewerRef.current) return;

    try {
      const viewer = new Cesium.Viewer(containerRef.current, {
        animation: false,
        timeline: false,
        navigationHelpButton: false,
        geocoder: false,
        homeButton: false,
        infoBox: false,
        sceneModePicker: false,
        selectionIndicator: false,
        baseLayerPicker: false,
        fullscreenButton: false,
      });

      Cesium.createWorldTerrainAsync().then(tp => {
         viewer.terrainProvider = tp;
      }).catch(e => console.error(e));



      // Start/End Markers
      if (data.length > 0) {
        viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(data[0].truth_lon, data[0].truth_lat, data[0].estimated_alt),
          point: { pixelSize: 8, color: Cesium.Color.LIME, outlineColor: Cesium.Color.BLACK, outlineWidth: 2 },
          label: { text: "START", font: '11px sans-serif', fillColor: Cesium.Color.WHITE, verticalOrigin: Cesium.VerticalOrigin.BOTTOM, pixelOffset: new Cesium.Cartesian2(0, -10) }
        });
        const last = data[data.length - 1];
        viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(last.truth_lon, last.truth_lat, last.estimated_alt),
          point: { pixelSize: 8, color: Cesium.Color.LIME, outlineColor: Cesium.Color.BLACK, outlineWidth: 2 },
          label: { text: "END", font: '11px sans-serif', fillColor: Cesium.Color.WHITE, verticalOrigin: Cesium.VerticalOrigin.BOTTOM, pixelOffset: new Cesium.Cartesian2(0, -10) }
        });
      }

      // Pre-calculate geography mapping correctly: Longitude, Latitude, Alt
      // Temporary Discontinuity Validation requested by user:
      
      const validatePath = (pathName: string, lonKey: keyof NavigationRecord, latKey: keyof NavigationRecord) => {
         const validCartesians: Cesium.Cartesian3[] = [];
         let lastLat = 0, lastLon = 0;
         for (let i = 0; i < data.length; i++) {
             const d = data[i];
             const lat = d[latKey] as number;
             const lon = d[lonKey] as number;
             
             if (i > 0) {
                 // Haversine approx for distance check
                 const dLat = (lat - lastLat) * Math.PI / 180;
                 const dLon = (lon - lastLon) * Math.PI / 180;
                 const a = Math.sin(dLat/2)*Math.sin(dLat/2) + Math.cos(lastLat*Math.PI/180)*Math.cos(lat*Math.PI/180) * Math.sin(dLon/2)*Math.sin(dLon/2);
                 const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                 const distance = 6371000 * c;
                 
                 // If the aircraft jumps more than 500 meters in 0.1 seconds (5000m/s = mach 15+), it's a data discontinuity
                 if (distance > 500) {
                    console.warn(`ABNORMAL JUMP DETECTED in ${pathName} at t=${d.timestamp}s`);
                    console.warn(`Prev: [${lastLat}, ${lastLon}] -> Curr: [${lat}, ${lon}]`);
                    console.warn(`Distance jumped physically impossible: ${distance.toFixed(1)} meters.`);
                    break; // Terminate line drawing at anomaly as per standard safety procedure
                 }
             }
             validCartesians.push(Cesium.Cartesian3.fromDegrees(lon, lat, d.estimated_alt));
             lastLat = lat;
             lastLon = lon;
         }
         return validCartesians;
      };

      const refCartesians = validatePath('REFERENCE', 'truth_lon', 'truth_lat');
      const insCartesians = validatePath('INS', 'ins_lon', 'ins_lat');
      const ekfCartesians = validatePath('TAN+EKF', 'estimated_lon', 'estimated_lat');

      // Initialize Entities using CallbackProperty to prevent React buffer rebuilds!
      refPathRef.current = viewer.entities.add({
        polyline: {
          positions: new Cesium.CallbackProperty(() => {
             const limit = currentTimeIndexRef.current + 1;
             return limit >= 2 ? refCartesians.slice(0, limit) : [];
          }, false),
          width: 2,
          material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.WHITE, dashLength: 16 }),
        }
      });
      
      insPathRef.current = viewer.entities.add({
        polyline: {
          positions: new Cesium.CallbackProperty(() => {
             const limit = currentTimeIndexRef.current + 1;
             return limit >= 2 ? insCartesians.slice(0, limit) : [];
          }, false),
          width: 2,
          material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.MAGENTA, dashLength: 16 }),
        }
      });

      ekfPathRef.current = viewer.entities.add({
        polyline: {
          positions: new Cesium.CallbackProperty(() => {
             const limit = currentTimeIndexRef.current + 1;
             return limit >= 2 ? ekfCartesians.slice(0, limit) : [];
          }, false),
          width: 3,
          material: Cesium.Color.LIME,
        }
      });

      aircraftRef.current = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(0, 0, 0),
        billboard: {
          image: svgIconURI,
          scale: 1.5,
          horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          rotation: 0 
        }
      });

      viewerRef.current = viewer;
    } catch (err) {
      console.error("CESIUM INITIALIZATION FAILED:", err);
      setHasError(true);
      onError();
    }
    
    return () => {
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, []);

  // Update entities smoothly without fully re-rendering arrays
  useEffect(() => {
    if (!viewerRef.current || hasError) return;
    if (currentTimeIndex === 0) return; 
    
    const currentState = data[currentTimeIndex];
    if (!currentState) return;
    
    const currentCartesian = Cesium.Cartesian3.fromDegrees(currentState.estimated_lon, currentState.estimated_lat, currentState.estimated_alt);

    if (aircraftRef.current) {
        aircraftRef.current.position = new Cesium.ConstantPositionProperty(currentCartesian);
        
        let hdg = 0;
        if (currentTimeIndex > 0) {
            const prev = data[currentTimeIndex - 1];
            const dy = currentState.estimated_lon - prev.estimated_lon;
            const dx = currentState.estimated_lat - prev.estimated_lat;
            if (dx !== 0 || dy !== 0) {
                hdg = (Math.atan2(dy, dx) * 180 / Math.PI);
                if (hdg < 0) hdg += 360;
            }
        }
        
        if (aircraftRef.current.billboard) {
            aircraftRef.current.billboard.rotation = new Cesium.ConstantProperty(-Cesium.Math.toRadians(hdg));
        }
    }

    const viewer = viewerRef.current;
    
    // Stable view offset matching Reference image oblique angle
    // Using ConstantProperty to ensure it doesn't jump
    const ENHANCED_OBLIQUE_OFFSET = new Cesium.Cartesian3(0.0, -1000.0, 1500.0);
    
    const aircraft = aircraftRef.current;
    if (aircraft && viewer.trackedEntity !== aircraft) {
        viewer.trackedEntity = aircraft;
        aircraft.viewFrom = new Cesium.ConstantProperty(ENHANCED_OBLIQUE_OFFSET);
    }

  }, [data, currentTimeIndex, hasError]);

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
  );
};
