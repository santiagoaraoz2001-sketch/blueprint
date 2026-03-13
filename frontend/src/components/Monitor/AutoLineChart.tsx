import { useMemo } from 'react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
} from 'recharts'
import { T, F, FS } from '@/lib/design-tokens'
import type { MetricPoint } from '@/stores/metricsStore'

interface AutoLineChartProps {
  data: MetricPoint[]
  color?: string
  height?: number
  xKey?: 'step' | 'timestamp'
  label?: string
  /** Second overlay series */
  overlay?: { data: MetricPoint[]; color: string; label: string }
  /** Show dashed lines for data gaps */
  showGaps?: boolean
}

interface ChartRow {
  step: number
  value: number | null
  overlayValue?: number | null
  isGap?: boolean
}

export default function AutoLineChart({
  data,
  color = '#00BFA5',
  height = 300,
  xKey = 'step',
  label,
  overlay,
  showGaps = true,
}: AutoLineChartProps) {
  const chartData = useMemo(() => {
    if (data.length === 0) return []

    const rows: ChartRow[] = data.map((p, i) => ({
      step: xKey === 'step' && p.step != null ? p.step : i,
      value: p.value,
    }))

    // Detect gaps: if step difference > 2x average interval, mark as gap
    if (showGaps && rows.length > 2) {
      const intervals = rows.slice(1).map((r, i) => r.step - rows[i].step)
      const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length
      for (let i = 1; i < rows.length; i++) {
        if (rows[i].step - rows[i - 1].step > avgInterval * 2) {
          rows[i].isGap = true
        }
      }
    }

    // Merge overlay data if present
    if (overlay && overlay.data.length > 0) {
      const overlayMap = new Map<number, number>()
      overlay.data.forEach((p, i) => {
        const key = xKey === 'step' && p.step != null ? p.step : i
        overlayMap.set(key, p.value)
      })
      for (const row of rows) {
        row.overlayValue = overlayMap.get(row.step) ?? null
      }
      // Add overlay-only points
      overlay.data.forEach((p, i) => {
        const key = xKey === 'step' && p.step != null ? p.step : i
        if (!rows.find((r) => r.step === key)) {
          rows.push({ step: key, value: null, overlayValue: p.value })
        }
      })
      rows.sort((a, b) => a.step - b.step)
    }

    return rows
  }, [data, overlay, xKey, showGaps])

  const latestValue = data.length > 0 ? data[data.length - 1].value : null

  if (chartData.length === 0) {
    return (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, animation: 'pulse 2s ease-in-out infinite' }}>
          Waiting for metrics...
        </span>
      </div>
    )
  }

  return (
    <div>
      {/* Latest value label above chart */}
      {label && latestValue != null && (
        <div style={{ marginBottom: 4, fontFamily: F, fontSize: FS.sm, color: T.text }}>
          {label}: <span style={{ color, fontWeight: 700 }}>{latestValue.toFixed(4)}</span>
        </div>
      )}

      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1A2332" />
          <XAxis
            dataKey="step"
            stroke="#64748B"
            tick={{ fontSize: 11, fontFamily: 'monospace' }}
          />
          <YAxis
            stroke="#64748B"
            tick={{ fontSize: 11, fontFamily: 'monospace' }}
          />
          <Tooltip
            contentStyle={{
              background: '#1A2332',
              border: '1px solid #2D3748',
              fontFamily: F,
              fontSize: FS.sm,
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            dot={false}
            strokeWidth={2}
            name={label || 'Value'}
            connectNulls={false}
          />
          {overlay && (
            <Line
              type="monotone"
              dataKey="overlayValue"
              stroke={overlay.color}
              dot={false}
              strokeWidth={2}
              name={overlay.label}
              connectNulls={false}
              strokeDasharray="5 3"
            />
          )}
          {/* Render gap indicators */}
          {showGaps &&
            chartData
              .filter((r) => r.isGap)
              .map((r) => (
                <ReferenceLine
                  key={`gap-${r.step}`}
                  x={r.step}
                  stroke="#F59E0B"
                  strokeDasharray="4 4"
                  label={{ value: '(data gap)', fill: '#F59E0B', fontSize: 9, fontFamily: F }}
                />
              ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
