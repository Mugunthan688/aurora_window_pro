import { MapContainer, TileLayer, Circle, CircleMarker, Marker, Popup, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import L from 'leaflet'
import { locationData, nearbyViewpoints, solarWindData } from '../data/mockData'

// Derive aurora oval latitude from Kp
const auroraLatitude = 77 - solarWindData.kpIndex * 2.5

// Custom SVG marker icons — avoids missing default Leaflet icon issue
function createIcon(color, pulse = false) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="28" height="36" viewBox="0 0 28 36">
      ${pulse ? `<circle cx="14" cy="14" r="13" fill="${color}" opacity="0.2"/>` : ''}
      <circle cx="14" cy="14" r="8" fill="${color}" opacity="0.9"/>
      <circle cx="14" cy="14" r="4" fill="white" opacity="0.95"/>
      <line x1="14" y1="22" x2="14" y2="34" stroke="${color}" stroke-width="2" opacity="0.7"/>
    </svg>
  `
  return L.divIcon({
    html: svg,
    iconSize: [28, 36],
    iconAnchor: [14, 34],
    popupAnchor: [0, -34],
    className: '',
  })
}

const userIcon      = createIcon('#27e8a7', true)
const viewpointIcon = createIcon('#00d4ff')
const bestIcon      = createIcon('#a78bfa')

// Aurora oval as a series of lat/lon points at the derived latitude
function buildOvalPoints(lat, steps = 72) {
  const pts = []
  for (let i = 0; i <= steps; i++) {
    const lon = -180 + (360 / steps) * i
    // Slight sinusoidal warp to mimic real oval asymmetry
    const warp = 2.5 * Math.sin((lon * Math.PI) / 180)
    pts.push([lat + warp, lon])
  }
  return pts
}

// Fit map to show user + aurora oval on mount
function AutoBounds({ center }) {
  const map = useMap()
  useEffect(() => {
    map.setView(center, 4)
  }, [map, center])
  return null
}

// Legend overlay rendered as a Leaflet control via a portal-like div
function MapLegend() {
  return (
    <div className="map-legend">
      <p className="map-legend__title">Map Legend</p>
      <div className="map-legend__item">
        <span className="map-legend__dot" style={{ background: '#27e8a7' }} />
        <span>Your Location</span>
      </div>
      <div className="map-legend__item">
        <span className="map-legend__dot" style={{ background: '#00d4ff' }} />
        <span>Viewpoint</span>
      </div>
      <div className="map-legend__item">
        <span className="map-legend__dot" style={{ background: '#a78bfa' }} />
        <span>Best Site</span>
      </div>
      <div className="map-legend__item">
        <span className="map-legend__dot map-legend__dot--ring" style={{ borderColor: '#27e8a7' }} />
        <span>Aurora Zone</span>
      </div>
      <div className="map-legend__item">
        <span className="map-legend__dot map-legend__dot--ring" style={{ borderColor: 'rgba(39,232,167,0.3)', background: 'rgba(39,232,167,0.08)' }} />
        <span>Activity Spread</span>
      </div>
      <div className="map-legend__kp">
        Kp {solarWindData.kpIndex} · Oval ~{Math.round(auroraLatitude)}°N
      </div>
    </div>
  )
}

export default function MapGlobe({ location, kpIndex, viewpoints }) {
  const center    = [location.lat, location.lon]
  const bestSite  = viewpoints.reduce((a, b) => (a.score > b.score ? a : b))

  // Aurora oval rings — layered for glow effect
  const ovalCenter   = [auroraLatitude, location.lon]
  const ovalRadiusKm = 350_000   // metres — approx width of oval band

  return (
    <div className="map-wrap">
      <MapContainer
        center={center}
        zoom={4}
        scrollWheelZoom={true}
        style={{ width: '100%', height: '100%' }}
        zoomControl={false}
      >
        {/* Dark CartoDB basemap — free, no API key */}
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
          subdomains="abcd"
          maxZoom={19}
        />

        <AutoBounds center={center} />

        {/* Aurora oval — outer diffuse glow */}
        <Circle
          center={ovalCenter}
          radius={ovalRadiusKm * 1.6}
          pathOptions={{
            color: 'rgba(39,232,167,0.08)',
            fillColor: 'rgba(39,232,167,0.04)',
            fillOpacity: 1,
            weight: 0,
          }}
        />

        {/* Aurora oval — mid band */}
        <Circle
          center={ovalCenter}
          radius={ovalRadiusKm}
          pathOptions={{
            color: 'rgba(39,232,167,0.25)',
            fillColor: 'rgba(39,232,167,0.08)',
            fillOpacity: 1,
            weight: 1.5,
            dashArray: '6 4',
          }}
        />

        {/* Aurora oval — bright core band */}
        <Circle
          center={ovalCenter}
          radius={ovalRadiusKm * 0.45}
          pathOptions={{
            color: 'rgba(39,232,167,0.7)',
            fillColor: 'rgba(39,232,167,0.15)',
            fillOpacity: 1,
            weight: 2,
          }}
        />

        {/* Soft aurora smear extending poleward */}
        <Circle
          center={[auroraLatitude + 4, location.lon]}
          radius={ovalRadiusKm * 0.7}
          pathOptions={{
            color: 'transparent',
            fillColor: 'rgba(167,139,250,0.07)',
            fillOpacity: 1,
            weight: 0,
          }}
        />

        {/* User location */}
        <Marker position={center} icon={userIcon}>
          <Popup className="map-popup">
            <strong>{location.name}</strong><br />
            Lat {location.lat}° · Lon {location.lon}°<br />
            Cloud cover: {location.cloudCover}%<br />
            Bortle: {location.lightPollution}<br />
            Local time: {location.localTime} {location.timezone}
          </Popup>
        </Marker>

        {/* Visibility radius around user */}
        <Circle
          center={center}
          radius={80_000}
          pathOptions={{
            color: 'rgba(39,232,167,0.3)',
            fillColor: 'rgba(39,232,167,0.05)',
            fillOpacity: 1,
            weight: 1,
          }}
        />

        {/* Nearby viewpoints */}
        {viewpoints.map((vp) => {
          const isBest = vp.id === bestSite.id
          return (
            <Marker
              key={vp.id}
              position={[vp.lat, vp.lon]}
              icon={isBest ? bestIcon : viewpointIcon}
            >
              <Popup className="map-popup">
                <strong>{vp.name}</strong>
                {isBest && <span className="map-popup__badge"> ★ Best</span>}
                <br />
                Score: {vp.score}/100<br />
                Distance: {vp.distance} km {vp.bearing}<br />
                Cloud cover: {vp.cloudCover}%<br />
                Bortle: {vp.bortle}<br />
                <em>{vp.note}</em>
              </Popup>
            </Marker>
          )
        })}

        {/* Dot markers for score context */}
        {viewpoints.map((vp) => (
          <CircleMarker
            key={`ring-${vp.id}`}
            center={[vp.lat, vp.lon]}
            radius={vp.score / 14}
            pathOptions={{
              color: vp.id === bestSite.id ? 'rgba(167,139,250,0.5)' : 'rgba(0,212,255,0.4)',
              fillColor: vp.id === bestSite.id ? 'rgba(167,139,250,0.12)' : 'rgba(0,212,255,0.1)',
              fillOpacity: 1,
              weight: 1,
            }}
          />
        ))}

      </MapContainer>

      {/* Legend sits on top of the map */}
      <MapLegend />
    </div>
  )
}