import { Navigation, MapPin, Clock, Cloud, Star, ChevronRight, Compass, TrendingUp } from 'lucide-react'
import { nearbyViewpoints, locationData } from '../data/mockData'

// Rough drive time estimate from straight-line distance
function estimateDriveTime(distanceKm) {
  const avgSpeedKph = 65
  const minutes     = Math.round((distanceKm / avgSpeedKph) * 60)
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

function openNavigation(lat, lon, name) {
  const url = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}&destination_place_id=${encodeURIComponent(name)}&travelmode=driving`
  window.open(url, '_blank', 'noopener,noreferrer')
}

function ScoreBar({ value }) {
  const color = value >= 90
    ? 'var(--aurora-green)'
    : value >= 75
      ? 'var(--aurora-cyan)'
      : '#f59e0b'

  return (
    <div className="score-bar">
      <div className="score-bar__track">
        <div
          className="score-bar__fill"
          style={{ width: `${value}%`, background: color, boxShadow: `0 0 6px ${color}60` }}
        />
      </div>
      <span className="score-bar__label" style={{ color }}>{value}</span>
    </div>
  )
}

function ViewpointRow({ vp, isBest, isSelected, onSelect }) {
  return (
    <button
      className={`viewpoint-row ${isSelected ? 'viewpoint-row--active' : ''} ${isBest ? 'viewpoint-row--best' : ''}`}
      onClick={() => onSelect(vp.id)}
    >
      <div className="viewpoint-row__left">
        {isBest
          ? <Star size={13} className="accent--violet" />
          : <MapPin size={13} style={{ color: 'rgba(255,255,255,0.3)' }} />
        }
        <div className="viewpoint-row__info">
          <span className="viewpoint-row__name">{vp.name}</span>
          <span className="viewpoint-row__meta">
            {vp.distance} km {vp.bearing} · {vp.cloudCover}% cloud
          </span>
        </div>
      </div>
      <div className="viewpoint-row__score-wrap">
        <span
          className="viewpoint-row__score"
          style={{ color: vp.score >= 90 ? 'var(--aurora-green)' : 'var(--aurora-cyan)' }}
        >
          {vp.score}
        </span>
        <ChevronRight size={12} style={{ color: 'rgba(255,255,255,0.2)' }} />
      </div>
    </button>
  )
}

import { useState } from 'react'

export default function RoutePanel({
  viewpoints      = nearbyViewpoints,
  currentLocation = locationData,
}) {
  const defaultBest = viewpoints.reduce((a, b) => (a.score > b.score ? a : b))
  const [selectedId, setSelectedId] = useState(defaultBest.id)

  const selected   = viewpoints.find((v) => v.id === selectedId) ?? defaultBest
  const driveTime  = estimateDriveTime(selected.distance)
  const isBest     = selected.id === defaultBest.id

  return (
    <div className="route-panel panel">

      {/* Header */}
      <div className="panel__header">
        <Navigation size={15} className="accent--cyan" />
        <h2 className="panel__title">Viewing Route</h2>
        {isBest && (
          <span className="best-badge">
            <Star size={10} />
            Best Site
          </span>
        )}
      </div>

      {/* Viewpoint selector list */}
      <div className="viewpoint-list">
        {viewpoints.map((vp) => (
          <ViewpointRow
            key={vp.id}
            vp={vp}
            isBest={vp.id === defaultBest.id}
            isSelected={vp.id === selectedId}
            onSelect={setSelectedId}
          />
        ))}
      </div>

      {/* Selected destination detail */}
      <div className="route-detail">
        <div className="route-detail__header">
          <Compass size={13} className="accent--cyan" />
          <span className="route-detail__title">{selected.name}</span>
        </div>

        <div className="route-stats">
          <div className="route-stat">
            <MapPin size={12} style={{ color: 'rgba(255,255,255,0.4)' }} />
            <span className="route-stat__label">Distance</span>
            <span className="route-stat__value">{selected.distance} km {selected.bearing}</span>
          </div>
          <div className="route-stat">
            <Clock size={12} style={{ color: 'rgba(255,255,255,0.4)' }} />
            <span className="route-stat__label">Drive Time</span>
            <span className="route-stat__value">{driveTime}</span>
          </div>
          <div className="route-stat">
            <Cloud size={12} style={{ color: 'rgba(255,255,255,0.4)' }} />
            <span className="route-stat__label">Cloud Cover</span>
            <span
              className="route-stat__value"
              style={{ color: selected.cloudCover < 20 ? 'var(--aurora-green)' : '#f59e0b' }}
            >
              {selected.cloudCover}%
            </span>
          </div>
          <div className="route-stat">
            <Star size={12} style={{ color: 'rgba(255,255,255,0.4)' }} />
            <span className="route-stat__label">Bortle Class</span>
            <span className="route-stat__value accent--violet">B{selected.bortle}</span>
          </div>
        </div>

        {/* Visibility score bar */}
        <div className="route-detail__score-row">
          <TrendingUp size={12} style={{ color: 'rgba(255,255,255,0.4)' }} />
          <span className="route-stat__label">Visibility Score</span>
          <ScoreBar value={selected.score} />
        </div>

        {/* Site note */}
        <p className="route-detail__note">{selected.note}</p>

        {/* CTA */}
        <button
          className="btn btn--primary btn--full"
          onClick={() => openNavigation(selected.lat, selected.lon, selected.name)}
        >
          <Navigation size={14} />
          Start Route to {selected.name.split(' ').slice(0, 2).join(' ')}
        </button>

        <p className="route-detail__disclaimer">
          Opens Google Maps · {currentLocation.name} → {selected.name}
        </p>
      </div>
    </div>
  )
}