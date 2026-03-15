import { Eye, Cloud, Moon, Star, Zap, MapPin } from 'lucide-react'

const STATUS_CONFIG = {
  EXCELLENT: { label: 'Excellent Chance',  color: 'var(--aurora-green)',  glow: 'rgba(39,232,167,0.25)'  },
  GOOD:      { label: 'Good Chance',       color: 'var(--aurora-cyan)',   glow: 'rgba(0,212,255,0.2)'    },
  MODERATE:  { label: 'Moderate Chance',   color: '#f59e0b',              glow: 'rgba(245,158,11,0.2)'   },
  POOR:      { label: 'Poor Conditions',   color: '#f87171',              glow: 'rgba(248,113,113,0.2)'  },
  NONE:      { label: 'No Activity',       color: 'rgba(255,255,255,0.3)', glow: 'rgba(255,255,255,0.05)' },
}

function deriveStatus(score) {
  if (score >= 80) return 'EXCELLENT'
  if (score >= 60) return 'GOOD'
  if (score >= 40) return 'MODERATE'
  if (score >= 20) return 'POOR'
  return 'NONE'
}

// Circular arc score indicator
function ScoreArc({ value, color, glow }) {
  const size     = 130
  const cx       = size / 2
  const cy       = size / 2
  const r        = 48
  // Arc spans 240° starting from 150° (bottom-left to bottom-right)
  const startDeg = 150
  const totalDeg = 240
  const deg      = (value / 100) * totalDeg

  function polarToXY(angleDeg, radius) {
    const rad = ((angleDeg - 90) * Math.PI) / 180
    return {
      x: cx + radius * Math.cos(rad),
      y: cy + radius * Math.sin(rad),
    }
  }

  function describeArc(startAngle, endAngle, radius) {
    const s    = polarToXY(startAngle, radius)
    const e    = polarToXY(endAngle, radius)
    const large = endAngle - startAngle > 180 ? 1 : 0
    return `M ${s.x} ${s.y} A ${radius} ${radius} 0 ${large} 1 ${e.x} ${e.y}`
  }

  const trackPath = describeArc(startDeg, startDeg + totalDeg, r)
  const fillPath  = deg > 0 ? describeArc(startDeg, startDeg + deg, r) : null

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="score-arc">
      {/* Glow filter */}
      <defs>
        <filter id="arc-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Track */}
      <path
        d={trackPath}
        fill="none"
        stroke="rgba(255,255,255,0.07)"
        strokeWidth="6"
        strokeLinecap="round"
      />

      {/* Fill */}
      {fillPath && (
        <path
          d={fillPath}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          filter="url(#arc-glow)"
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
      )}

      {/* Score value */}
      <text
        x={cx} y={cy - 4}
        textAnchor="middle"
        fill={color}
        fontSize="28"
        fontWeight="700"
        fontFamily="var(--font-display)"
        style={{ filter: `drop-shadow(0 0 8px ${glow})` }}
      >
        {value}
      </text>
      <text
        x={cx} y={cy + 16}
        textAnchor="middle"
        fill="rgba(255,255,255,0.4)"
        fontSize="10"
        fontFamily="var(--font-mono)"
        letterSpacing="1.5"
      >
        SCORE
      </text>
    </svg>
  )
}

// Single factor bar row
function FactorRow({ icon: Icon, label, value, score, accent }) {
  const barColor = score >= 75
    ? 'var(--aurora-green)'
    : score >= 50
      ? 'var(--aurora-cyan)'
      : score >= 30
        ? '#f59e0b'
        : '#f87171'

  return (
    <div className="factor-row">
      <div className="factor-row__label">
        <Icon size={12} style={{ color: barColor, flexShrink: 0 }} />
        <span>{label}</span>
      </div>
      <div className="factor-row__bar-wrap">
        <div className="factor-row__bar-track">
          <div
            className="factor-row__bar-fill"
            style={{
              width: `${score}%`,
              background: barColor,
              boxShadow: `0 0 6px ${barColor}60`,
            }}
          />
        </div>
        <span className="factor-row__value" style={{ color: barColor }}>{value}</span>
      </div>
    </div>
  )
}

// Default props for standalone use
const defaultScore = {
  overall: 82,
  factors: {
    kp:            90,
    cloudCover:    85,
    moonlight:     95,
    latitude:      88,
    lightPollution: 78,
  },
  status:  'EXCELLENT',
  message: 'Prime conditions. Aurora likely visible overhead.',
}

const defaultLocation = {
  name:         'Fairbanks, AK',
  cloudCover:   18,
  lightPollution: 2,
  moonPhase:    0.12,
  lat:          64.8,
  lon:         -147.7,
}

export default function VisibilityCard({
  score    = defaultScore,
  location = defaultLocation,
}) {
  const statusKey = score.status || deriveStatus(score.overall)
  const status    = STATUS_CONFIG[statusKey] || STATUS_CONFIG.MODERATE

  const factors = [
    {
      icon:   Zap,
      label:  'Kp Activity',
      value:  `${score.factors.kp}%`,
      score:  score.factors.kp,
    },
    {
      icon:   Cloud,
      label:  'Cloud Cover',
      value:  `${location.cloudCover}% cover`,
      score:  score.factors.cloudCover,
    },
    {
      icon:   Moon,
      label:  'Moon Interference',
      value:  `${Math.round(location.moonPhase * 100)}% illum.`,
      score:  score.factors.moonlight,
    },
    {
      icon:   MapPin,
      label:  'Mag. Latitude',
      value:  `${location.lat.toFixed(1)}°N`,
      score:  score.factors.latitude,
    },
    {
      icon:   Star,
      label:  'Sky Darkness',
      value:  `Bortle ${location.lightPollution}`,
      score:  score.factors.lightPollution,
    },
  ]

  return (
    <div
      className="visibility-card panel"
      style={{ '--status-glow': status.glow, '--status-color': status.color }}
    >
      {/* Header */}
      <div className="panel__header">
        <Eye size={15} style={{ color: status.color }} />
        <h2 className="panel__title">Visibility Score</h2>
        <span
          className="status-badge"
          style={{ color: status.color, borderColor: `${status.color}40`, background: `${status.color}12` }}
        >
          {status.label}
        </span>
      </div>

      {/* Score arc + location */}
      <div className="visibility-card__top">
        <ScoreArc value={score.overall} color={status.color} glow={status.glow} />
        <div className="visibility-card__meta">
          <p className="visibility-card__location">
            <MapPin size={11} style={{ opacity: 0.5 }} />
            {location.name}
          </p>
          <p
            className="visibility-card__message"
            style={{ color: status.color }}
          >
            {score.message}
          </p>
          <div className="visibility-card__coords">
            {location.lat.toFixed(2)}°N · {Math.abs(location.lon).toFixed(2)}°W
          </div>
        </div>
      </div>

      {/* Factor breakdown */}
      <div className="visibility-card__factors">
        <p className="visibility-card__factors-label">Factor Breakdown</p>
        {factors.map((f) => (
          <FactorRow key={f.label} {...f} />
        ))}
      </div>
    </div>
  )
}