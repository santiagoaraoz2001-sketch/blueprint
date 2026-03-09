import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from 'recharts'
import type { RunRow } from './ResultsTable'

interface MetricChartProps {
  runs: RunRow[]
}

export default function MetricChart({ runs }: MetricChartProps) {
  // Collect all metric keys
  const metricKeys = useMemo(() => {
    const keys = new Set<string>()
    runs.forEach((r) => {
      if (r.metrics) Object.keys(r.metrics).forEach((k) => keys.add(k))
    })
    return Array.from(keys).filter((k) => {
      // Only include numeric metrics
      return runs.some((r) => typeof r.metrics?.[k] === 'number')
    })
  }, [runs])

  const [xAxis, setXAxis] = useState<string>('_index')
  const [yAxis, setYAxis] = useState<string>(metricKeys[0] || '')
  const [chartType, setChartType] = useState<'scatter' | 'line'>('scatter')

  const axisOptions = ['_index', '_duration', ...metricKeys]

  const chartData = useMemo(() => {
    return runs
      .map((r, i) => {
        const getVal = (key: string) => {
          if (key === '_index') return i
          if (key === '_duration') return r.duration_seconds || 0
          return r.metrics?.[key] ?? null
        }
        const x = getVal(xAxis)
        const y = getVal(yAxis)
        if (x == null || y == null) return null
        return { x, y, id: r.id, status: r.status }
      })
      .filter(Boolean) as { x: number; y: number; id: string; status: string }[]
  }, [runs, xAxis, yAxis])

  if (metricKeys.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
          No numeric metrics available to chart
        </span>
      </div>
    )
  }

  // Update yAxis when metricKeys change
  if (!yAxis && metricKeys.length > 0) {
    setYAxis(metricKeys[0])
  }

  const selectStyle: React.CSSProperties = {
    background: T.surface2,
    border: `1px solid ${T.border}`,
    color: T.sec,
    fontFamily: F,
    fontSize: FS.sm,
    padding: '3px 6px',
    outline: 'none',
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Controls */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '8px 12px',
          borderBottom: `1px solid ${T.border}`,
        }}
      >
        <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>X</label>
        <select value={xAxis} onChange={(e) => setXAxis(e.target.value)} style={selectStyle}>
          {axisOptions.map((k) => (
            <option key={k} value={k}>
              {k === '_index' ? 'Run #' : k === '_duration' ? 'Duration' : k}
            </option>
          ))}
        </select>

        <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>Y</label>
        <select value={yAxis} onChange={(e) => setYAxis(e.target.value)} style={selectStyle}>
          {axisOptions.filter((k) => k !== '_index').map((k) => (
            <option key={k} value={k}>
              {k === '_duration' ? 'Duration' : k}
            </option>
          ))}
        </select>

        <div style={{ flex: 1 }} />

        <div style={{ display: 'flex', gap: 2 }}>
          {(['scatter', 'line'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setChartType(t)}
              style={{
                padding: '2px 8px',
                background: chartType === t ? T.surface4 : T.surface2,
                border: `1px solid ${chartType === t ? T.borderHi : T.border}`,
                color: chartType === t ? T.text : T.dim,
                fontFamily: F,
                fontSize: FS.xxs,
                textTransform: 'uppercase',
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div style={{ flex: 1, padding: 12 }}>
        <ResponsiveContainer width="100%" height="100%">
          {chartType === 'scatter' ? (
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
              <XAxis
                dataKey="x"
                type="number"
                stroke={T.dim}
                tick={{ fill: T.dim, fontSize: 8, fontFamily: F }}
                label={{ value: xAxis === '_index' ? 'Run #' : xAxis, position: 'bottom', fill: T.dim, fontSize: 8 }}
              />
              <YAxis
                dataKey="y"
                type="number"
                stroke={T.dim}
                tick={{ fill: T.dim, fontSize: 8, fontFamily: F }}
                label={{ value: yAxis, angle: -90, position: 'insideLeft', fill: T.dim, fontSize: 8 }}
              />
              <Tooltip
                contentStyle={{
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                  fontFamily: F,
                  fontSize: 8,
                  color: T.sec,
                }}
              />
              <Scatter data={chartData} fill={T.cyan} />
            </ScatterChart>
          ) : (
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
              <XAxis
                dataKey="x"
                stroke={T.dim}
                tick={{ fill: T.dim, fontSize: 8, fontFamily: F }}
              />
              <YAxis
                dataKey="y"
                stroke={T.dim}
                tick={{ fill: T.dim, fontSize: 8, fontFamily: F }}
              />
              <Tooltip
                contentStyle={{
                  background: T.surface2,
                  border: `1px solid ${T.border}`,
                  fontFamily: F,
                  fontSize: 8,
                  color: T.sec,
                }}
              />
              <Line type="monotone" dataKey="y" stroke={T.cyan} dot={{ fill: T.cyan, r: 3 }} />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}
