import { useState } from 'react'
import { Activity, Wind, Cloud, Moon, Zap, Radio, RefreshCw } from 'lucide-react'

import MapGlobe from '../components/MapGlobe'
import VisibilityCard from '../components/VisibilityCard'
import AlertBanner from '../components/AlertBanner'
import RoutePanel from '../components/RoutePanel'

import {
  solarWindData,
  locationData,
  visibilityScore,
  alerts,
  nearbyViewpoints,
} from '../data/mockData'

const telemetry = [
  {
    icon: Activity,
    label: 'IMF Bz',
    value: `${solarWindData.bz} nT`,
    accent: solarWindData.bz < 0 ? 'green' : 'red',
    title: 'Negative Bz is favorable for aurora activity',
  },
  {
    icon: Wind,
    label: 'Solar Wind',
    value: `${solarWindData.speed} km/s`,
    accent: 'cyan',
    title: 'Solar wind velocity from DSCOVR L1',
  },
  {
    icon: Zap,
    label: 'Kp Index',
    value: solarWindData.kpIndex.toFixed(1),
    accent: 'violet',
    title: 'Planetary geomagnetic activity index (0–9)',
  },
  {
    icon: Cloud,
    label: 'Cloud Cover',
    value: `${locationData.cloudCover}%`,
    accent: locationData.cloudCover < 30 ? 'green' : 'amber',
    title: 'Local cloud cover at your position',
  },
  {
    icon: Moon,
    label: 'Moon Illum.',
    value: `${Math.round(locationData.moonPhase * 100)}%`,
    accent: locationData.moonPhase < 0.3 ? 'green' : 'amber',
    title: 'Lunar illumination — lower is better for aurora viewing',
  },
]

export default function LiveMap() {
  const [lastRefresh, setLastRefresh] = useState(new Date())

  const handleRefresh = () => {
    // Replace with live data fetch when API is ready
    setLastRefresh(new Date())
  }

  const refreshTime = lastRefresh.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

  return (
    <div className="livemap">

      {/* ── Page Header ──────────────────────────────────── */}
      <header className="livemap__header">
        <div className="livemap__header-left">
          <div className="live-pill">
            <Radio size={11} />
            <span>LIVE</span>
          </div>
          <div>
            <h1 className="livemap__title">Aurora Operations Map</h1>
            <p className="livemap__subtitle">
              {locationData.name} · {locationData.localTime} {locationData.timezone} · Kp {solarWindData.kpIndex}
            </p>
          </div>
        </div>

        <button className="refresh-btn" onClick={handleRefresh} title="Refresh data">
          <RefreshCw size={14} />
          <span>Updated {refreshTime}</span>
        </button>
      </header>

      {/* ── Telemetry Strip ──────────────────────────────── */}
      <div className="telemetry-strip">
        {telemetry.map(({ icon: Icon, label, value, accent, title }) => (
          <div key={label} className="telemetry-chip" title={title}>
            <Icon size={13} className={`telemetry-chip__icon accent--${accent}`} />
            <span className="telemetry-chip__label">{label}</span>
            <span className={`telemetry-chip__value accent--${accent}`}>{value}</span>
          </div>
        ))}
      </div>

      {/* ── Main Content: Map + Side Panel ───────────────── */}
      <div className="livemap__body">

        {/* Map */}
        <div className="livemap__map-wrap">
          <MapGlobe
            location={locationData}
            kpIndex={solarWindData.kpIndex}
            viewpoints={nearbyViewpoints}
          />
        </div>

        {/* Side panel */}
        <aside className="livemap__sidebar">
          <VisibilityCard score={visibilityScore} location={locationData} />
          <AlertBanner alerts={alerts} />
          <RoutePanel viewpoints={nearbyViewpoints} currentLocation={locationData} />
        </aside>

      </div>
    </div>
  )
}