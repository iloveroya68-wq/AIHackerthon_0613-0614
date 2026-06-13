/**
 * MapProvider — adapter for swappable map backends.
 */
import React from "react";
import type { GeoJSONFeatureCollection, SearchZoneProperties, Coordinate } from "@/types/contracts";

export interface MapProps {
  center: [number, number];           // [lon, lat]
  zoom?: number;
  searchZones?: GeoJSONFeatureCollection<SearchZoneProperties>;
  lastKnownPosition?: Coordinate;     // last signal dot
  driftTrack?: Coordinate[];          // positions up to selected time step
  driftSector?: {                     // uncertainty cone from origin
    origin: Coordinate;
    directionDeg: number;
    halfAngleDeg: number;
    distanceNm: number;
  };
  particles?: [number, number][];     // debug: [[lon, lat], ...]
  onMapClick?: (coord: Coordinate) => void;
  onMouseMove?: (coord: Coordinate) => void;
  pickMode?: boolean;
  className?: string;
}

type MapBackend = "leaflet" | "kakao";
const BACKEND: MapBackend =
  (import.meta.env.VITE_MAP_BACKEND as MapBackend | undefined) ?? "leaflet";

const LeafletMap = React.lazy(() => import("./LeafletMap"));

export const DriftMap: React.FC<MapProps> = (props) => {
  if (BACKEND === "leaflet") {
    return (
      <React.Suspense fallback={<div className="h-full bg-navy-900 animate-pulse" />}>
        <LeafletMap {...props} />
      </React.Suspense>
    );
  }
  return (
    <div className="h-full bg-navy-900 flex items-center justify-center text-cyan-400">
      Kakao Maps adapter not yet implemented
    </div>
  );
};
