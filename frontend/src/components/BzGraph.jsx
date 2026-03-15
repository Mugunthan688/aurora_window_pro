import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, Legend
} from 'recharts'
import { Activity } from 'lucide-react'
import { bzHistory, speedHistory, solarWindData } from '../data/mockData'

// Merge Bz and speed into a single dataset keyed by timestamp
const chartData = bzHistory.map((point, i) => ({
  t:     `${Math.abs(point.t)}m`,
  bz:    point.bz,
  speed: speedHistory[i]?.v ?? null,
}))

// Custom tooltip
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__time">{label} ago</p>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="chart-tooltip__row">
          <span
            className="chart-tooltip__dot"
            style={{ background: entry.color }}
          />
          <span className="chart-tooltip__key">
            {entry.dataKey === 'bz' ? 'IMF Bz' : 'Solar Wind'}
          </span>
          <span className="chart-tooltip__val" style={{ color: entry.color }}>
            {entry.dataKey === 'bz'
              ? `${entry.value.toFixed(1)} nT`
              : `${entry.value} km/s`}
          </span>
        </div>
      ))}
    </div>
  )
}

// Status pill derived from current Bz
function BzStatus({ bz }) {
  let label, accent
  if (bz < -10)      { label = 'Very Favorable';  accent = 'green'  }
  else if (bz < -5)  { label = 'Favorable';        accent = 'cyan'   }
  else if (bz < 0)   { label = 'Marginal';         accent = 'amber'  }
  else               { label = 'Unfavorable';       accent = 'red'    }

  return (
    <span className={`bz-status accent--${accent}`}>
      <span className={`bz-status__dot accent-bg--${accent}`} />
      {label}
    </span>
  )
}

export default function BzGraph() {
  return (
    <div className="panel bz-panel">

      {/* Header */}
      <div className="panel__header">
        <Activity size={15} className="accent--green" />
        <h2 className="panel__title">IMF Bz &amp; Solar Wind — Last 60 min</h2>
        <BzStatus bz={solarWindData.bz} />
      </div>

      <p className="panel__sub">
        Sustained negative Bz (southward IMF) couples solar wind energy into Earth's
        magnetosphere — the primary driver of auroral activity. Values below −5 nT
        significantly increase aurora probability.
      </p>

      {/* Live readout row */}
      <div className="bz-readouts">
        <div className="bz-readout">
          <span className="bz-readout__label">Current Bz</span>
          <span className={`bz-readout__value ${solarWindData.bz < 0 ? 'accent--green' : 'accent--red'}`}>
            {solarWindData.bz > 0 ? '+' : ''}{solarWindData.bz} nT
          </span>
        </div>
        <div className="bz-readout">
          <span className="bz-readout__label">Solar Wind</span>
          <span className="bz-readout__value accent--cyan">{solarWindData.speed} km/s</span>
        </div>
        <div className="bz-readout">
          <span className="bz-readout__label">Bt (Total)</span>
          <span className="bz-readout__value accent--violet">{solarWindData.bt} nT</span>
        </div>
        <div className="bz-readout">
          <span className="bz-readout__label">Density</span>
          <span className="bz-readout__value" style={{ color: 'var(--text-secondary)' }}>
            {solarWindData.density} p/cm³
          </span>
        </div>
      </div>

      {/* Chart */}
      <div className="bz-chart">
        <ResponsiveContainer width="100%" height={240}>
          <LineChart
            data={chartData}
            margin={{ top: 10, right: 12, left: -10, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.05)"
              vertical={false}
            />

            <XAxis
              dataKey="t"
              tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
              interval={2}
              reversed
            />

            {/* Left Y axis — Bz */}
            <YAxis
              yAxisId="bz"
              domain={[-18, 8]}
              tick={{ fill: 'rgba(255,255,255,0.35)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}`}
            />

            {/* Right Y axis — Speed */}
            <YAxis
              yAxisId="speed"
              orientation="right"
              domain={[380, 680]}
              tick={{ fill: 'rgba(0,212,255,0.4)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}`}
            />

            <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1 }} />

            <Legend
              wrapperStyle={{ paddingTop: '12px', fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'rgba(255,255,255,0.5)' }}
              formatter={(value) => value === 'bz' ? 'IMF Bz (nT)' : 'Solar Wind (km/s)'}
            />

            {/* Bz threshold — strong aurora coupling */}
            <ReferenceLine
              yAxisId="bz"
              y={-7}
              stroke="rgba(39,232,167,0.45)"
              strokeDasharray="5 3"
              label={{
                value: '−7 nT threshold',
                fill: 'rgba(39,232,167,0.6)',
                fontSize: 10,
                fontFamily: 'var(--font-mono)',
                position: 'insideTopLeft',
              }}
            />

            {/* Zero line */}
            <ReferenceLine
              yAxisId="bz"
              y={0}
              stroke="rgba(255,255,255,0.12)"
              strokeDasharray="2 4"
            />

            {/* Speed threshold */}
            <ReferenceLine
              yAxisId="speed"
              y={500}
              stroke="rgba(0,212,255,0.3)"
              strokeDasharray="5 3"
              label={{
                value: '500 km/s',
                fill: 'rgba(0,212,255,0.5)',
                fontSize: 10,
                fontFamily: 'var(--font-mono)',
                position: 'insideTopRight',
              }}
            />

            {/* Bz line */}
            <Line
              yAxisId="bz"
              type="monotone"
              dataKey="bz"
              stroke="#27e8a7"
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 4, fill: '#27e8a7', stroke: 'var(--bg-card)', strokeWidth: 2 }}
              style={{ filter: 'drop-shadow(0 0 4px rgba(39,232,167,0.5))' }}
            />

            {/* Solar wind speed line */}
            <Line
              yAxisId="speed"
              type="monotone"
              dataKey="speed"
              stroke="#00d4ff"
              strokeWidth={1.8}
              strokeDasharray="6 3"
              dot={false}
              activeDot={{ r: 4, fill: '#00d4ff', stroke: 'var(--bg-card)', strokeWidth: 2 }}
              opacity={0.75}
            />

          </LineChart>
        </ResponsiveContainer>
      </div>

    </div>
  )
}