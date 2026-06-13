/**
 * Korea land-mask utility.
 * Loads /korea.geojson once, pre-computes per-feature bounding boxes,
 * then provides fast isOnLand(lon, lat) checks via ray-casting.
 */

interface ProcessedFeature {
  minX: number; minY: number; maxX: number; maxY: number;
  rings: GeoJSON.Position[][];
}

interface LandCache {
  geojson: GeoJSON.FeatureCollection;
  features: ProcessedFeature[];
}

let cache: LandCache | null = null;
let loadPromise: Promise<LandCache> | null = null;

function processFeatures(geojson: GeoJSON.FeatureCollection): ProcessedFeature[] {
  return geojson.features.map((f) => {
    const geom = f.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon;
    // Normalize both types to Position[][][] (array of polygons, each a ring-array)
    const polygonList: GeoJSON.Position[][][] =
      geom.type === "Polygon"
        ? [geom.coordinates]   // Position[][] → [Position[][]]
        : geom.coordinates;    // already Position[][][]

    const rings: GeoJSON.Position[][] = [];
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

    for (const polygonRings of polygonList) {
      const outerRing = polygonRings[0]; // outer ring
      rings.push(outerRing);
      for (const pos of outerRing) {
        const x = pos[0], y = pos[1];
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
    return { minX, minY, maxX, maxY, rings };
  });
}

/** Fetch and pre-process once; returns the raw GeoJSON for map rendering. */
export function loadKoreaGeoJSON(): Promise<GeoJSON.FeatureCollection> {
  if (cache) return Promise.resolve(cache.geojson);
  if (loadPromise) return loadPromise.then((c) => c.geojson);

  loadPromise = fetch("/korea.geojson")
    .then((r) => r.json() as Promise<GeoJSON.FeatureCollection>)
    .then((geojson) => {
      cache = { geojson, features: processFeatures(geojson) };
      return cache;
    });

  return loadPromise.then((c) => c.geojson);
}

function raycast(lon: number, lat: number, ring: GeoJSON.Position[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/**
 * Returns true if the point (lon, lat) falls inside Korean land.
 * Must await loadKoreaGeoJSON() before calling this.
 */
export function isOnLand(lon: number, lat: number): boolean {
  if (!cache) return false;
  for (const f of cache.features) {
    if (lon < f.minX || lon > f.maxX || lat < f.minY || lat > f.maxY) continue;
    for (const ring of f.rings) {
      if (raycast(lon, lat, ring)) return true;
    }
  }
  return false;
}

/**
 * Strict land check for a grid cell: returns true if the center OR any corner
 * touches land. Catches cells whose center sits just offshore but whose body
 * overlaps coastline (e.g. Busan harbour cells).
 */
export function cellOverlapsLand(coords: GeoJSON.Position[]): boolean {
  const cx = (coords[0][0] + coords[2][0]) / 2;
  const cy = (coords[0][1] + coords[2][1]) / 2;
  return [
    [cx, cy],
    coords[0], coords[1], coords[2], coords[3],
  ].some(([lon, lat]) => isOnLand(lon, lat));
}
