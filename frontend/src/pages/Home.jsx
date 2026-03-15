import { Link } from 'react-router-dom'
import {
  Zap, MapPin, Eye, Bell, Navigation, Wind,
  Activity, Cloud, Star, ChevronRight, Radio
} from 'lucide-react'
import { solarWindData, locationData, visibilityScore } from '../data/mockData'

const features = [
  {
    icon: Activity,
    title: 'Live Solar Wind',
    desc: 'Real-time Bz, Bt, density and velocity data streamed from NOAA DSCOVR. See exactly what the magnetosphere is doing right now.',
    accent: 'green',
  },
  {
    icon: Eye,
    title: 'Visibility Scoring',
    desc: 'A composite score factoring Kp index, cloud cover, moon phase, light pollution, and your magnetic latitude — tailored to your GPS location.',
    accent: 'cyan',
  },
  {
    icon: MapPin,
    title: 'Dark-Sky Routing',
    desc: 'Get turn-by-turn suggestions to the nearest optimal viewing site — ranked by darkness, horizon quality, and live cloud cover.',
    accent: 'violet',
  },
  {
    icon: Bell,
    title: 'Smart Alerts',
    desc: 'Geomagnetic storm watches, Bz threshold alerts, and substorm notifications delivered the moment conditions change.',
    accent: 'amber',
  },
  {
    icon: Navigation,
    title: 'Aurora Oval Map',
    desc: 'Live Kp-adjusted auroral oval overlay on an interactive map with your position, cloud opacity, and nearby viewpoint markers.',
    accent: 'cyan',
  },
]

const steps = [
  { n: '01', title: 'Set Your Location', body: 'Grant GPS or enter coordinates. Aurora Window Pro resolves your magnetic latitude and local sky conditions instantly.' },
  { n: '02', title: 'Read the Conditions', body: 'The dashboard synthesises solar wind, Kp, clouds, and moonlight into a single Visibility Score and plain-English status.' },
  { n: '03', title: 'Act on Guidance', body: 'Follow the route suggestion to your nearest dark-sky viewpoint or monitor the live map as the oval expands toward you.' },
]

export default function Home() {
  const bz = solarWindData.bz
  const bzFavorable = bz < 0

  return (
    <div className="home">

      {/* ── Hero ─────────────────────────────────────────── */}
      <section className="hero">
        <div className="hero__badge">
          <Radio size={12} />
          <span>Live · {locationData.localTime} {locationData.timezone}</span>
        </div>

        <h1 className="hero__title">
          Aurora<br />
          <span className="hero__title--accent">Window Pro</span>
        </h1>

        <p className="hero__sub">
          Hyper-local aurora intelligence for photographers and chasers.
          Know exactly when, where, and how well you'll see the lights —
          before you leave your door.
        </p>

        <div className="hero__ctas">
          <Link to="/live-map" className="btn btn--primary">
            <MapPin size={16} />
            Open Live Map
          </Link>
          <Link to="/dashboard" className="btn btn--ghost">
            <Activity size={16} />
            View Dashboard
            <ChevronRight size={15} />
          </Link>
        </div>
      </section>

      {/* ── Live Stats Strip ─────────────────────────────── */}
      <section className="stats-strip">
        <div className="stat-chip">
          <Wind size={14} className="stat-chip__icon stat-chip__icon--cyan" />
          <span className="stat-chip__label">Solar Wind</span>
          <span className="stat-chip__value">{solarWindData.speed} km/s</span>
        </div>
        <div className="stat-chip">
          <Activity size={14} className={`stat-chip__icon ${bzFavorable ? 'stat-chip__icon--green' : 'stat-chip__icon--red'}`} />
          <span className="stat-chip__label">IMF Bz</span>
          <span className={`stat-chip__value ${bzFavorable ? 'val--green' : 'val--red'}`}>
            {bz > 0 ? '+' : ''}{bz} nT
          </span>
        </div>
        <div className="stat-chip">
          <Zap size={14} className="stat-chip__icon stat-chip__icon--violet" />
          <span className="stat-chip__label">Kp Index</span>
          <span className="stat-chip__value">{solarWindData.kpIndex}</span>
        </div>
        <div className="stat-chip">
          <Star size={14} className="stat-chip__icon stat-chip__icon--green" />
          <span className="stat-chip__label">Visibility</span>
          <span className="stat-chip__value val--green">{visibilityScore.overall}%</span>
        </div>
        <div className="stat-chip">
          <Cloud size={14} className="stat-chip__icon stat-chip__icon--cyan" />
          <span className="stat-chip__label">Cloud Cover</span>
          <span className="stat-chip__value">{locationData.cloudCover}%</span>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────── */}
      <section className="section">
        <div className="section__header">
          <h2 className="section__title">Everything a chaser needs</h2>
          <p className="section__sub">
            Built for real field conditions — readable in the dark, fast on mobile.
          </p>
        </div>

        <div className="features-grid">
          {features.map(({ icon: Icon, title, desc, accent }) => (
            <div key={title} className={`feature-card feature-card--${accent}`}>
              <div className={`feature-card__icon feature-card__icon--${accent}`}>
                <Icon size={20} />
              </div>
              <h3 className="feature-card__title">{title}</h3>
              <p className="feature-card__desc">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How It Works ─────────────────────────────────── */}
      <section className="section">
        <div className="section__header">
          <h2 className="section__title">How it works</h2>
          <p className="section__sub">Three steps from your couch to the perfect shot.</p>
        </div>

        <div className="steps">
          {steps.map(({ n, title, body }) => (
            <div key={n} className="step">
              <div className="step__number">{n}</div>
              <div className="step__content">
                <h3 className="step__title">{title}</h3>
                <p className="step__body">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ───────────────────────────────────── */}
      <section className="cta-banner">
        <div className="cta-banner__inner">
          <h2 className="cta-banner__title">
            Conditions are&nbsp;
            <span className="val--green">{visibilityScore.status.toLowerCase()}</span>
            &nbsp;right now
          </h2>
          <p className="cta-banner__sub">{visibilityScore.message}</p>
          <div className="hero__ctas">
            <Link to="/live-map" className="btn btn--primary">
              <MapPin size={16} />
              Open Live Map
            </Link>
            <Link to="/dashboard" className="btn btn--ghost">
              <Activity size={16} />
              View Dashboard
              <ChevronRight size={15} />
            </Link>
          </div>
        </div>
      </section>

    </div>
  )
}