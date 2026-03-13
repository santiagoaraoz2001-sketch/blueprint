import { useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, EMPTY_BLOCK_METRICS, type MetricSeries } from '@/stores/metricsStore'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

interface AutoLineChartProps {
  metricName: string
  blockId: string
  color?: string
  height?: number
  title?: string
  /** Show dashed lines for data gaps */
  showGaps?: boolean
  /** Additional metric to overlay */
  overlayMetric?: string
  overlayColor?: string
}

/** Detects gaps in step sequence that are > 2x the average interval */
function segmentWithGaps(series: MetricSeries[]): { data: any[]; gapIndices: number[] } {
  if (series.length < 3) return { data: series.map(s => ({ step: s.step, value: s.value })), gapIndices: [] }

  const intervals: number[] = []
  for (let i = 1; i < series.length; i++) {
    intervals.push(series[i].step - series[i - 1].step)
  }
  const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length

  const data: any[] = []
  const gapIndices: number[] = []

  for (let i = 0; i < series.length; i++) {
    if (i > 0 && (series[i].step - series[i - 1].step) > avgInterval * 2) {
      gapIndices.push(data.length)
      // Insert a gap marker
      data.push({
        step: Math.round((series[i - 1].step + series[i].step) / 2),
        value: undefined,
        gap: true,
      })
    }
    data.push({ step: series[i].step, value: series[i].value })
  }

  return { data, gapIndices }
}

export default function AutoLineChart({
  metricName, blockId, color = '#00BFA5', height = 200,
  title, showGaps = true, overlayMetric, overlayColor = '#F59E0B',
}: AutoLineChartProps) {
  const blockMetrics = useMetricsStore((s) => s.metrics[blockId] ?? EMPTY_BLOCK_METRICS)
  const series = blockMetrics[metricName] || []
  const overlaySeries = overlayMetric ? (blockMetrics[overlayMetric] || []) : []

  const chartData = useMemo(() => {
    if (series.length === 0) return []

    const { data } = showGaps ? segmentWithGaps(series) : { data: series.map(s => ({ step: s.step, value: s.value })) }

    // Merge overlay data by step
    if (overlaySeries.length > 0) {
      const overlayMap = new Map(overlaySeries.map(s => [s.step, s.value]))
      return data.map(d => ({
        ...d,
        overlay: overlayMap.get(d.step),
      }))
    }

    return data
  }, [series, overlaySeries, showGaps])

  if (chartData.length === 0) {
    return (
      <div style={{
        height, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          Waiting for {metricName}...
        </span>
      </div>
    )
  }

  return (
    <div style={{ height }}>
      {title && (
        <div style={{
          padding: '4px 8px',
          fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
          color: T.sec, letterSpacing: '0.06em',
        }}>
          {title}
        </div>
      )}
      <ResponsiveContainer width="100%" height={title ? height - 20 : height}>
        <LineChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1A2332" />
          <XAxis
            dataKey="step"
            stroke={T.dim}
            tick={{ fill: T.dim, fontSize: 7, fontFamily: F }}
          />
          <YAxis
            stroke={T.dim}
            tick={{ fill: T.dim, fontSize: 7, fontFamily: F }}
            width={45}
          />
          <Tooltip
            contentStyle={{
              background: T.surface2,
              border: `1px solid ${T.borderHi}`,
              fontFamily: F, fontSize: 7, color: T.sec,
              padding: '4px 8px',
            }}
            labelStyle={{ fontFamily: F, fontSize: 7, color: T.dim }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3, fill: color }}
            isAnimationActive={false}
            connectNulls={false}
            name={metricName}
          />
          {overlayMetric && overlaySeries.length > 0 && (
            <Line
              type="monotone"
              dataKey="overlay"
              stroke={overlayColor}
              strokeWidth={1.5}
              strokeDasharray="4 2"
              dot={false}
              activeDot={{ r: 3, fill: overlayColor }}
              isAnimationActive={false}
              connectNulls={false}
              name={overlayMetric}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
