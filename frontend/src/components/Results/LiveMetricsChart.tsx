import { useState, useMemo, useRef, useEffect } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

/** A single data point for one step */
export interface MetricsDataPoint {
  step: number
  [metricName: string]: number
}

interface LiveMetricsChartProps {
  /** Ordered array of metric data points (one per training step) */
  data: MetricsDataPoint[]
  /** Metric names to display as separate colored lines. If empty, auto-detect from data keys. */
  metricNames?: string[]
  /** Chart title */
  title?: string
}

const LINE_COLORS = [
  '#4af6c3', // cyan/green
  '#6C9EFF', // blue
  '#B87EFF', // purple
  '#FB923C', // orange
  '#F472B6', // pink
  '#FBBF24', // yellow
  '#22c55e', // green
  '#ff433d', // red
]

export default function LiveMetricsChart({
  data,
  metricNames,
  title = 'Live Metrics',
}: LiveMetricsChartProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  // Auto-detect metric names from data keys (exclude 'step')
  const resolvedMetrics = useMemo(() => {
    if (metricNames && metricNames.length > 0) return metricNames
    const keys = new Set<string>()
    data.forEach((point) => {
      Object.keys(point).forEach((k) => {
        if (k !== 'step') keys.add(k)
      })
    })
    return Array.from(keys)
  }, [data, metricNames])

  // Visibility toggles for each metric line
  const [hiddenMetrics, setHiddenMetrics] = useState<Set<string>>(new Set())

  const toggleMetric = (name: string) => {
    setHiddenMetrics((prev) => {
      const next = new Set(prev)
      if (next.has(name)) {
        next.delete(name)
      } else {
        next.add(name)
      }
      return next
    })
  }

  // Auto-scroll to latest data
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth
    }
  }, [data, autoScroll])

  if (data.length === 0) {
    return (
      <div
        style={{
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
          Waiting for metrics data...
        </span>
      </div>
    )
  }

  // Calculate chart width: grow when many steps
  const minWidth = Math.max(400, data.length * 8)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '6px 12px',
          borderBottom: `1px solid ${T.border}`,
          gap: 8,
        }}
      >
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xs,
            fontWeight: 700,
            color: T.text,
            letterSpacing: '0.08em',
          }}
        >
          {title}
        </span>

        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {data.length} steps
        </span>

        <div style={{ flex: 1 }} />

        {/* Auto-scroll toggle */}
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          style={{
            padding: '1px 6px',
            background: autoScroll ? `${T.cyan}15` : T.surface2,
            border: `1px solid ${autoScroll ? `${T.cyan}40` : T.border}`,
            color: autoScroll ? T.cyan : T.dim,
            fontFamily: F,
            fontSize: FS.xxs,
            cursor: 'pointer',
            letterSpacing: '0.06em',
          }}
        >
          AUTO-SCROLL {autoScroll ? 'ON' : 'OFF'}
        </button>
      </div>

      {/* Legend with toggles */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
          padding: '6px 12px',
          borderBottom: `1px solid ${T.border}`,
        }}
      >
        {resolvedMetrics.map((name, i) => {
          const color = LINE_COLORS[i % LINE_COLORS.length]
          const hidden = hiddenMetrics.has(name)
          return (
            <button
              key={name}
              onClick={() => toggleMetric(name)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 6px',
                background: hidden ? T.surface2 : `${color}15`,
                border: `1px solid ${hidden ? T.border : `${color}40`}`,
                cursor: 'pointer',
                opacity: hidden ? 0.4 : 1,
                transition: 'all 0.12s',
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 2,
                  background: color,
                  display: 'inline-block',
                }}
              />
              <span
                style={{
                  fontFamily: F,
                  fontSize: FS.xxs,
                  color: hidden ? T.dim : color,
                  letterSpacing: '0.04em',
                }}
              >
                {name}
              </span>
            </button>
          )
        })}
      </div>

      {/* Chart area with horizontal scroll */}
      <div
        ref={scrollRef}
        style={{ flex: 1, overflowX: 'auto', overflowY: 'hidden', padding: '8px 4px 4px 4px' }}
      >
        <div style={{ width: Math.max(minWidth, 400), height: '100%', minHeight: 160 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
              <XAxis
                dataKey="step"
                stroke={T.dim}
                tick={{ fill: T.dim, fontSize: 7, fontFamily: F }}
                label={{
                  value: 'Step',
                  position: 'insideBottom',
                  offset: -2,
                  fill: T.dim,
                  fontSize: 7,
                  fontFamily: F,
                }}
              />
              <YAxis
                stroke={T.dim}
                tick={{ fill: T.dim, fontSize: 7, fontFamily: F }}
                width={40}
              />
              <Tooltip
                contentStyle={{
                  background: T.surface2,
                  border: `1px solid ${T.borderHi}`,
                  fontFamily: F,
                  fontSize: 7,
                  color: T.sec,
                  padding: '4px 8px',
                }}
                labelStyle={{ fontFamily: F, fontSize: 7, color: T.dim }}
              />
              <Legend content={() => null} />
              {resolvedMetrics
                .filter((name) => !hiddenMetrics.has(name))
                .map((name) => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={LINE_COLORS[resolvedMetrics.indexOf(name) % LINE_COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    activeDot={{ r: 3, fill: LINE_COLORS[resolvedMetrics.indexOf(name) % LINE_COLORS.length] }}
                    isAnimationActive={false}
                  />
                ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
