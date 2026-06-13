import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Polyline, Polygon, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import type { MapProps } from "./MapProvider";
import type { SearchZoneProperties, Coordinate } from "@/types/contracts";

// Fix default icon paths broken by bundler
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const ZONE_COLORS: Record<1 | 2 | 3, string> = {
  1: "#ef4444",
  2: "#f97316",
  3: "#eab308",
};
const ZONE_LABELS: Record<1 | 2 | 3, string> = {
  1: "1순위 (60%)",
  2: "2순위 (80%)",
  3: "3순위 (95%)",
};

function zoneStyle(priority: number) {
  const color = ZONE_COLORS[priority as 1 | 2 | 3] ?? "#ffffff";
  return { color, fillColor: color, fillOpacity: 0.15, weight: 2, opacity: 0.9 };
}

function buildSectorPositions(
  origin: Coordinate,
  dirDeg: number,
  halfDeg: number,
  distNm: number,
): [number, number][] {
  const cosLat = Math.cos((origin.lat * Math.PI) / 180);
  const ARC_STEPS = 20;
  const pts: [number, number][] = [[origin.lat, origin.lon]];
  for (let i = 0; i <= ARC_STEPS; i++) {
    const angle = dirDeg - halfDeg + (2 * halfDeg * i) / ARC_STEPS;
    const rad = (angle * Math.PI) / 180;
    const lat = origin.lat + (distNm * Math.cos(rad)) / 60;
    const lon = origin.lon + (distNm * Math.sin(rad)) / (60 * cosLat);
    pts.push([lat, lon]);
  }
  return pts;
}

function RecenterView({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();
  const previousZoom = useRef(zoom);
  const lat = center[0];
  const lon = center[1];

  useEffect(() => {
    if (previousZoom.current !== zoom) {
      previousZoom.current = zoom;
      map.setView([lat, lon], zoom, { animate: false });
      return;
    }

    const current = map.getCenter();
    if (Math.abs(current.lat - lat) > 1e-7 || Math.abs(current.lng - lon) > 1e-7) {
      map.panTo([lat, lon], { animate: false });
    }
  }, [lat, lon, map, zoom]);
  return null;
}

function MapClickHandler({
  onMapClick,
  onMouseMove,
}: {
  onMapClick?: (c: Coordinate) => void;
  onMouseMove?: (c: Coordinate) => void;
}) {
  useMapEvents({
    click(e) { onMapClick?.({ lat: e.latlng.lat, lon: e.latlng.lng }); },
    mousemove(e) { onMouseMove?.({ lat: e.latlng.lat, lon: e.latlng.lng }); },
  });
  return null;
}

export default function LeafletMap({
  center, zoom = 10,
  searchZones,
  lastKnownPosition, driftTrack, driftSector,
  particles,
  onMapClick, onMouseMove, pickMode,
  className,
}: MapProps) {
  const leafletCenter: [number, number] = [center[1], center[0]];

  const trackPositions: [number, number][] = driftTrack
    ? driftTrack.map((c) => [c.lat, c.lon])
    : [];

  const fullTrack: [number, number][] =
    lastKnownPosition && trackPositions.length > 0
      ? [[lastKnownPosition.lat, lastKnownPosition.lon], ...trackPositions]
      : trackPositions;

  return (
    <MapContainer
      center={leafletCenter}
      zoom={zoom}
      className={className ?? "h-full w-full"}
      style={{ background: "#0a1628", cursor: pickMode ? "crosshair" : undefined }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        opacity={0.55}
      />
      <RecenterView center={leafletCenter} zoom={zoom} />
      {(onMapClick || onMouseMove) && (
        <MapClickHandler onMapClick={onMapClick} onMouseMove={onMouseMove} />
      )}

      {/* Drift uncertainty sector (fan from origin) */}
      {driftSector && driftSector.distanceNm > 0 && (
        <Polygon
          positions={buildSectorPositions(
            driftSector.origin,
            driftSector.directionDeg,
            driftSector.halfAngleDeg,
            driftSector.distanceNm,
          )}
          pathOptions={{
            color: "#22d3ee",
            fillColor: "#22d3ee",
            fillOpacity: 0.10,
            weight: 1.5,
            dashArray: "6 4",
            opacity: 0.55,
          }}
        />
      )}

      {/* Search zones — priority 3→2→1 순서로 렌더 (1순위가 맨 위) */}
      {searchZones && (() => {
        const sorted = {
          ...searchZones,
          features: [...searchZones.features].sort(
            (a, b) =>
              (b.properties as SearchZoneProperties).priority -
              (a.properties as SearchZoneProperties).priority,
          ),
        };
        return (
          <GeoJSON
            key={JSON.stringify(searchZones)}
            data={sorted as unknown as GeoJSON.FeatureCollection}
            style={(feature) => {
              const props = feature?.properties as SearchZoneProperties | undefined;
              return zoneStyle(props?.priority ?? 3);
            }}
            onEachFeature={(feature, layer) => {
              const props = feature.properties as SearchZoneProperties;
              layer.bindTooltip(
                `${ZONE_LABELS[props.priority as 1 | 2 | 3]} · ${props.area_km2.toFixed(1)} km²`,
                { permanent: false, className: "drift-tooltip" },
              );
            }}
          />
        );
      })()}

      {/* Debug particles */}
      {particles?.map(([lon, lat], i) => (
        <CircleMarker
          key={i}
          center={[lat, lon]}
          radius={2}
          pathOptions={{ color: "#a78bfa", fillColor: "#a78bfa", fillOpacity: 0.7, weight: 0 }}
        />
      ))}

      {/* Drift track (dotted path) */}
      {fullTrack.length >= 2 && (
        <Polyline
          positions={fullTrack}
          pathOptions={{
            color: "#22d3ee",
            weight: 1.5,
            dashArray: "6 5",
            opacity: 0.65,
          }}
        />
      )}

      {/* Last known position — amber pulsing ring */}
      {lastKnownPosition && (
        <>
          <CircleMarker
            center={[lastKnownPosition.lat, lastKnownPosition.lon]}
            radius={10}
            pathOptions={{
              color: "#f59e0b",
              fillColor: "#f59e0b",
              fillOpacity: 0.15,
              weight: 2,
              dashArray: "4 3",
            }}
          />
          <CircleMarker
            center={[lastKnownPosition.lat, lastKnownPosition.lon]}
            radius={4}
            pathOptions={{
              color: "#f59e0b",
              fillColor: "#f59e0b",
              fillOpacity: 1,
              weight: 0,
            }}
          />
        </>
      )}
    </MapContainer>
  );
}
