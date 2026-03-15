import {
  Camera, Compass, Clock, Moon, Star, AlertTriangle,
  Eye, Cloud, Zap, Activity, TrendingUp, CheckCircle
} from 'lucide-react'

import BzGraph from '../components/BzGraph'
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

const summaryCards = [
  {
    icon: Zap,
    label: 'Aurora Probability',
    value: `${visibilityScore.overall}%`,
    sub: visibilityScore.status,
    accent: 'green',
  },
  {
    icon: Eye,
    label: 'Visibility Score',
    value: visibilityScore.overall,
    sub: 'Composite index',
    accent: 'cyan',
    isScore: true,
  },
  {
    icon: Cloud,
    label: 'Cloud Cover',
    value: `${locationData.cloudCover}%`,
    sub: locationData.cloudCover < 30 ? 'Clear skies' : 'Partly cloudy',
    accent: locationData.cloudCover < 30 ? 'green' : 'amber',
  },
  {
    icon: Star,
    label: 'Bortle Class',
    value: `B${locationData.lightPollution}`,
    sub: locationData.lightPollution <= 2 ? 'Truly dark sky' : 'Rural sky',
    accent: 'violet',
  },
  {
    icon: Moon,
    label: 'Moon Illumination',
    value: `${Math.round(locationData.moonPhase * 100)}%`,
    sub: locationData.moonPhase < 0.2 ? 'New moon — ideal' : 'Low interference',
    accent: locationData.moonPhase < 0.3 ? 'green' : 'amber',
  },
  {
    icon: AlertTriangle,
    label: 'Alert Status',
    value: 'G2 Watch',
    sub: 'Storm in progress',
    accent: 'amber',
  },
]

const photoSettings = [
  { label: 'ISO',           value: '1600–3200',    note: 'Start at 1600, push to 3200 if Kp > 5' },
  { label: 'Shutter Speed', value: '8–15 s',       note: 'Shorter for fast-moving corona' },
  { label: 'Aperture',      value: 'f/1.8–f/2.8',  note: 'Widest available lens setting' },
  { label: 'Focus',         value: 'Manual ∞',     note: 'Live-view on a bright star to confirm' },
  { label: 'White Balance', value: '3500–4200 K',  note: 'Tungsten / custom for natural green cast' },
  { label: 'Format',        value: 'RAW',          note: 'Essential for post-processing latitude' },
]

const fieldAdvice = [
  {
    icon: Compass,
    label: 'Best Viewing Direction',
    value: 'North-Northwest',
    detail: 'Aurora oval currently centered 8° above magnetic north from your position.',
    accent: 'cyan',
  },
  {
    icon: Clock,
    label: 'Suggested Departure',
    value: 'Now — 22:30',
    detail: 'Bz has been southward 45+ min. Peak activity likely within the next 90 minutes.',
    accent: 'green',
  },
  {
    icon: Star,
    label: 'Darkness Quality',
    value: 'Excellent',
    detail: `Astronomical twilight ended at 20:12. Sun is ${Math.abs(locationData.sunAltitude)}° below horizon.`,
    accent: 'violet',
  },
  {
    icon: TrendingUp,
    label: 'Activity Trend',
    value: 'Intensifying',
    detail: `Solar wind rising (${solarWindData.speed} km/s). Bz sustained at ${solarWindData.bz} nT. Expect elevated substorm risk.`,
    accent: 'amber',
  },
]

function ScoreRing({ value }) {
  const r = 20
  const circ = 2 * Math.PI * r
  const fill = circ - (value / 100) * circ
  return (
    <svg width="52" height="52" viewBox="0 0 52 52" className="score-ring">
      <circle cx="26" cy="26" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4" />
      <circle
        cx="26" cy="26" r={r}
        fill="none"
        stroke="var(--aurora-cyan)"
        strokeWidth="4"
        strokeDasharray={circ}
        strokeDashoffset={fill}
        strokeLinecap="round"
        transform="rotate(-90 26 26)"
        style={{ filter: 'drop-shadow(0 0 4px var(--aurora-cyan))' }}
      />
      <text x="26" y="30" textAnchor="middle" fill="var(--aurora-cyan)"
        fontSize="11" fontFamily="var(--font-mono)" fontWeight="500">
        {value}
      </text>
    </svg>
  )
}

export default function Dashboard() {
  return (
    <div className="dashboard">

      {/* ── Header ───────────────────────────────────────── */}
      <header className="dashboard__header">
        <div>
          <h1 className="dashboard__title">Mission Dashboard</h1>
          <p className="dashboard__subtitle">
            {locationData.name} · {locationData.localTime} {locationData.timezone} · Kp {solarWindData.kpIndex} · {visibilityScore.status}
          </p>
        </div>
        <div className="dashboard__status">
          <CheckCircle size={15} className="accent--green" />
          <span className="accent--green" style={{ fontSize: '0.78rem', fontFamily: 'var(--font-mono)' }}>
            Systems nominal
          </span>
        </div>
      </header>

      {/* ── Summary Cards ────────────────────────────────── */}
      <div className="summary-grid">
        {summaryCards.map(({ icon: Icon, label, value, sub, accent, isScore }) => (
          <div key={label} className={`summary-card summary-card--${accent}`}>
            <div className="summary-card__top">
              <span className="summary-card__label">{label}</span>
              <Icon size={14} className={`accent--${accent}`} />
            </div>
            {isScore ? (
              <div className="summary-card__score-row">
                <span className={`summary-card__value accent--${accent}`}>{value}</span>
                <ScoreRing value={Number(value)} />
              </div>
            ) : (
              <span className={`summary-card__value accent--${accent}`}>{value}</span>
            )}
            <span className="summary-card__sub">{sub}</span>
          </div>
        ))}
      </div>

      {/* ── Main Grid: Graph + Sidebar ───────────────────── */}
      <div className="dashboard__main">

        {/* Left column */}
        <div className="dashboard__left">
          <BzGraph />

          {/* Photographer Recommendations */}
          <section className="panel">
            <div className="panel__header">
              <Camera size={15} className="accent--cyan" />
              <h2 className="panel__title">Photographer Intelligence</h2>
            </div>

            <div className="field-advice-grid">
              {fieldAdvice.map(({ icon: Icon, label, value, detail, accent }) => (
                <div key={label} className={`advice-card advice-card--${accent}`}>
                  <div className="advice-card__header">
                    <Icon size={14} className={`accent--${accent}`} />
                    <span className="advice-card__label">{label}</span>
                  </div>
                  <span className={`advice-card__value accent--${accent}`}>{value}</span>
                  <p className="advice-card__detail">{detail}</p>
                </div>
              ))}
            </div>

            {/* Photo Settings Table */}
            <div className="photo-settings">
              <div className="photo-settings__header">
                <Activity size={13} className="accent--violet" />
                <span>Recommended Camera Settings — Kp {solarWindData.kpIndex}</span>
              </div>
              <div className="photo-settings__table">
                {photoSettings.map(({ label, value, note }) => (
                  <div key={label} className="photo-row">
                    <span className="photo-row__label">{label}</span>
                    <span className="photo-row__value">{value}</span>
                    <span className="photo-row__note">{note}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>

        {/* Right sidebar */}
        <aside className="dashboard__sidebar">
          <VisibilityCard score={visibilityScore} location={locationData} />
          <AlertBanner alerts={alerts} />
          <RoutePanel viewpoints={nearbyViewpoints} currentLocation={locationData} />
        </aside>

      </div>
    </div>
  )
}