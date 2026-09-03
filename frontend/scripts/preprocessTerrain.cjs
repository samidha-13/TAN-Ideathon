const fs = require('fs');
const path = require('path');
const GeoTIFF = require('geotiff');

const missions = {
  mountain: {
    lat_min: 30.00, lat_max: 30.30,
    lon_min: 78.00, lon_max: 78.45,
    tiff: '../../terrain/mountain/n30_e078_1arc_v3.tif',
    tileLat: 30, tileLon: 78
  },
  desert: {
    lat_min: 26.50, lat_max: 27.00,
    lon_min: 70.50, lon_max: 71.00,
    tiff: '../../terrain/desert/n26_e070_1arc_v3.tif',
    tileLat: 26, tileLon: 70
  },
  western_ghats: {
    lat_min: 15.00, lat_max: 15.50,
    lon_min: 73.70, lon_max: 74.20,
    tiff: '../../terrain/western_ghats/n15_e073_1arc_v3.tif',
    tileLat: 15, tileLon: 73
  },
  flat_plain: {
    lat_min: 25.00, lat_max: 25.50,
    lon_min: 81.50, lon_max: 82.00,
    tiff: '../../terrain/flat_plain/n25_e081_1arc_v3.tif',
    tileLat: 25, tileLon: 81
  }
};

async function processMission(key, config) {
  console.log(`Processing ${key}...`);
  const tiffPath = path.resolve(__dirname, config.tiff);
  if (!fs.existsSync(tiffPath)) {
    console.error(`File not found: ${tiffPath}`);
    return;
  }
  
  const tiff = await GeoTIFF.fromFile(tiffPath);
  const image = await tiff.getImage();
  const raster = await image.readRasters({ interleave: false });
  const data = raster[0]; // Assuming first band is elevation
  const width = image.getWidth();   // Usually 3601
  const height = image.getHeight(); // Usually 3601
  
  // SRTM pixel (0,0) is top-left (Lat + 1, Lon)
  const degPerPixel = 1.0 / (width - 1);
  
  const getElevation = (lat, lon) => {
    // Top is tileLat + 1
    const yDeg = (config.tileLat + 1) - lat;
    const xDeg = lon - config.tileLon;
    
    let y = Math.max(0, Math.min(height - 1, Math.round(yDeg / degPerPixel)));
    let x = Math.max(0, Math.min(width - 1, Math.round(xDeg / degPerPixel)));
    
    return data[y * width + x];
  };

  const resolution = 150;
  const lats = [];
  for(let i = 0; i < resolution; i++) {
    // Latitude from top (max) to bottom (min)
    lats.push(config.lat_max - (config.lat_max - config.lat_min) * (i / (resolution - 1)));
  }
  
  const lons = [];
  for(let i = 0; i < resolution; i++) {
    lons.push(config.lon_min + (config.lon_max - config.lon_min) * (i / (resolution - 1)));
  }
  
  const elevations = [];
  let minElev = Infinity, maxElev = -Infinity;
  
  for (const lat of lats) {
    const row = [];
    for (const lon of lons) {
      let elev = getElevation(lat, lon);
      if (elev < -1000 || elev > 9000) elev = 0;
      row.push(elev);
      minElev = Math.min(minElev, elev);
      maxElev = Math.max(maxElev, elev);
    }
    elevations.push(row);
  }
  
  const outData = {
    mission: key,
    bounds: { lat_min: config.lat_min, lat_max: config.lat_max, lon_min: config.lon_min, lon_max: config.lon_max },
    resolution,
    min_elevation: minElev,
    max_elevation: maxElev,
    data: elevations
  };
  
  const outDir = path.resolve(__dirname, '../public/terrain');
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }
  
  const outPath = path.join(outDir, `${key}_heightmap.json`);
  fs.writeFileSync(outPath, JSON.stringify(outData));
  
  console.log(`Saved ${outPath}. Min: ${minElev}, Max: ${maxElev}`);
}

async function main() {
  for (const [key, config] of Object.entries(missions)) {
    await processMission(key, config);
  }
}

main().catch(console.error);
