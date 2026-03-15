import { AlertTriangle, CheckCircle, Info, XCircle, Radio, Bell } from 'lucide-react'

const SEVERITY_CONFIG = {
  success: {
    icon:       CheckCircle,
    chipLabel:  'Active',
    chipClass:  'chip--green',
    cardClass:  'alert--success',
    iconColor:  'var(--aurora-green)',
  },
  watch: {
    icon:       AlertTriangle,
    chipLabel:  'Watch',
    chipClass:  'chip--amber',
    cardClass:  'alert--watch',
    iconColor:  '#f59e0b',
  },
  danger: {
    icon:       XCircle,
    chipLabel:  'Triggered',
    chipClass:  'chip--red',
    cardClass:  'alert--danger',
    iconColor:  '#f87171',
  },
  info: {
    icon:       Info,
    chipLabel:  'Live',
    chipClass:  'chip--cyan',
    cardClass:  'alert--info',
    iconColor:  'var(--aurora-cyan)',
  },
}

// Map legacy alert levels from mockData to severity keys
function normaliseSeverity(level) {
  if (!level) return 'info'
  const map = { watch: 'watch', danger: 'danger', success: 'success', info: 'info', warning: 'watch' }
  return map[level] ?? 'info'
}

const defaultAlerts = [
  {
    id:       1,
    level:    'watch',
    title:    'G2 Geomagnetic Storm Watch',
    body:     'NOAA forecasts G2 conditions between 22:00–04:00 local time.',
    issued:   '20:45',
  },
  {
    id:       2,
    level:    'info',
    title:    'Bz Sustained Southward',
    body:     'IMF Bz has been negative >10 nT for 45 minutes. Enhanced substorm activity expected.',
    issued:   '21:30',
  },
]

function AlertItem({ title, body, severity = 'info', timestamp }) {
  const config = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.info
  const Icon   = config.icon

  return (
    <div className={`alert-item ${config.cardClass}`}>
      <div className="alert-item__left">
        <Icon size={16} style={{ color: config.iconColor, flexShrink: 0, marginTop: 1 }} />
      </div>
      <div className="alert-item__body">
        <div className="alert-item__header">
          <span className="alert-item__title">{title}</span>
          <span className={`alert-chip ${config.chipClass}`}>
            <span className="alert-chip__dot" />
            {config.chipLabel}
          </span>
        </div>
        <p className="alert-item__message">{body}</p>
        {timestamp && (
          <span className="alert-item__time">{timestamp}</span>
        )}
      </div>
    </div>
  )
}

export default function AlertBanner({ alerts = defaultAlerts }) {
  const hasAlerts = alerts && alerts.length > 0

  return (
    <div className="alert-banner panel">
      <div className="panel__header">
        <Bell size={15} className="accent--amber" />
        <h2 className="panel__title">Active Alerts</h2>
        {hasAlerts && (
          <span className="alert-count">
            <Radio size={10} />
            {alerts.length} live
          </span>
        )}
      </div>

      <div className="alert-list">
        {hasAlerts ? (
          alerts.map((alert) => (
            <AlertItem
              key={alert.id}
              title={alert.title}
              body={alert.body}
              severity={normaliseSeverity(alert.level)}
              timestamp={alert.issued ? `Issued ${alert.issued}` : undefined}
            />
          ))
        ) : (
          <div className="alert-empty">
            <CheckCircle size={18} className="accent--green" />
            <span>No active alerts — conditions nominal</span>
          </div>
        )}
      </div>
    </div>
  )
}