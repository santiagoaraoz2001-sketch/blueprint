import { useState, useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, type MetricPoint } from '@/stores/metricsStore'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { Download, ToggleLeft, ToggleRight } from 'lucide-react'

interface TrainingDashboardProps {
  runId: string
  blockId: string
}

const CHART_COLORS = ['#4af6c3', '#3B82F6', '#f59e0b', '#8B5CF6', '#EC4899', '#22c55e', '#fb8b1e', '#ff433d']

function insertGapPoints(series: MetricPoint[]): (MetricPoint | null)[] {
  if (series.length < 3) return series
  const intervals = series.slice(1).map((p, i) => p.step - series[i].step)
  const sorted = [...intervals].sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length / 2)] || 1
  const result: (MetricPoint | null)[] = []
  for (let i = 0; i < series.length; i++) {
    result.push(series[i])
    if (i < series.length - 1) {
      const gap = series[i + 1].step - series[i].step
      if (gap > median * 2) {
        result.push(null)
      }
    }
  }
  return result
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div
      style={{
        background: T.surface2,
        border: `1px solid ${T.border}`,
        padding: '6px 10px',
        fontFamily: F,
        fontSize: FS.xxs,
      }}
    >
      <div style={{ color: T.dim, marginBottom: 2 }}>Step {label}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.dataKey}: {typeof p.value === 'number' ? p.value.toFixed(6) : p.value}
        </div>
      ))}
    </div>
  )
}

export default function TrainingDashboard({ runId, blockId }: TrainingDashboardProps) {
  const [rawMode, setRawMode] = useState(false)
  const blockMetrics = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.metrics)
  const block = useMetricsStore((s) => s.runs[runId]?.blocks[blockId])

  const allMetricNames = useMemo(() => blockMetrics ? Object.keys(blockMetrics) : [], [blockMetrics])

  // Get all series data directly from blockMetrics
  const allSeries = useMemo(() => {
    if (!blockMetrics) return {} as Record<string, MetricPoint[]>
    const result: Record<string, MetricPoint[]> = {}
    for (const name of allMetricNames) {
      result[name] = blockMetrics[name] || []
    }
    return result
  }, [blockMetrics, allMetricNames])

  // Categorize metrics
  const lossMetrics = allMetricNames.filter((n) => n.toLowerCase().includes('loss'))
  const lrMetrics = allMetricNames.filter((n) => n.toLowerCase().includes('lr') || n.toLowerCase().includes('learning_rate'))
  const otherMetrics = allMetricNames.filter((n) => !lossMetrics.includes(n) && !lrMetrics.includes(n))

  // Build unified chart data for loss metrics
  const lossChartData = useMemo(() => {
    if (lossMetrics.length === 0) return []
    const allSteps = new Set<number>()
    lossMetrics.forEach((name) => {
      const series = allSeries[name] || []
      const withGaps = insertGapPoints(series)
      withGaps.forEach((p) => { if (p) allSteps.add(p.step) })
    })
    const steps = [...allSteps].sort((a, b) => a - b)
    return steps.map((step) => {
      const point: Record<string, any> = { step }
      lossMetrics.forEach((name) => {
        const series = allSeries[name] || []
        const match = series.find((p) => p.step === step)
        point[name] = match ? match.value : undefined
      })
      return point
    })
  }, [lossMetrics, allSeries])

  // Latest values
  const latestValues = useMemo(() => {
    const result: Record<string, number | null> = {}
    for (const name of allMetricNames) {
      const series = allSeries[name] || []
      result[name] = series.length > 0 ? series[series.length - 1].value : null
    }
    return result
  }, [allMetricNames, allSeries])

  const exportCSV = () => {
    if (allMetricNames.length === 0) return
    const allSteps = new Set<number>()
    allMetricNames.forEach((name) => {
      (allSeries[name] || []).forEach((p) => allSteps.add(p.step))
    })
    const steps = [...allSteps].sort((a, b) => a - b)
    const header = ['step', ...allMetricNames].join(',')
    const rows = steps.map((step) => {
      const vals = allMetricNames.map((name) => {
        const match = (allSeries[name] || []).find((p) => p.step === step)
        return match ? match.value : ''
      })
      return [step, ...vals].join(',')
    })
    const csv = [header, ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `metrics-${runId}-${blockId}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (allMetricNames.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          fontFamily: F,
          fontSize: FS.xs,
          color: T.dim,
        }}
      >
        Waiting for training metrics...
      </div>
    )
  }

  if (rawMode) {
    // Raw data table
    const allPoints: { step: number; name: string; value: number; timestamp: number }[] = []
    allMetricNames.forEach((name) => {
      (allSeries[name] || []).forEach((p) => {
        allPoints.push({ step: p.step, name, value: p.value, timestamp: p.timestamp })
      })
    })
    allPoints.sort((a, b) => a.timestamp - b.timestamp)

    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: `1px solid ${T.border}`, flexShrink: 0 }}>
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700 }}>Raw Data</span>
          <div style={{ flex: 1 }} />
          <button
            onClick={() => setRawMode(false)}
            style={{ background: 'none', border: 'none', color: T.cyan, cursor: 'pointer', fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <ToggleRight size={12} /> Charts
          </button>
          <button
            onClick={exportCSV}
            style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <Download size={10} /> CSV
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 0 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: F, fontSize: FS.xxs }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim, fontWeight: 600 }}>Time</th>
                <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim, fontWeight: 600 }}>Step</th>
                <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim, fontWeight: 600 }}>Metric</th>
                <th style={{ padding: '4px 8px', textAlign: 'right', color: T.dim, fontWeight: 600 }}>Value</th>
              </tr>
            </thead>
            <tbody>
              {allPoints.map((p, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                  <td style={{ padding: '3px 8px', color: T.dim }}>{new Date(p.timestamp).toLocaleTimeString()}</td>
                  <td style={{ padding: '3px 8px', color: T.sec }}>{p.step}</td>
                  <td style={{ padding: '3px 8px', color: T.cyan }}>{p.name}</td>
                  <td style={{ padding: '3px 8px', color: T.text, textAlign: 'right' }}>{p.value.toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', padding: '8px 12px', gap: 16 }}>
      {/* Header with controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700 }}>
          Training — {block?.label || blockId}
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => setRawMode(true)}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <ToggleLeft size={12} /> Raw Data
        </button>
        <button
          onClick={exportCSV}
          style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', fontFamily: F, fontSize: FS.xxs, display: 'flex', alignItems: 'center', gap: 4 }}
        >
          <Download size={10} /> CSV
        </button>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', flexShrink: 0 }}>
        {allMetricNames.slice(0, 6).map((name) => (
          <div
            key={name}
            style={{
              padding: '6px 10px',
              background: T.surface1,
              border: `1px solid ${T.border}`,
              minWidth: 100,
            }}
          >
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 2 }}>{name}</div>
            <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700 }}>
              {latestValues[name] != null ? latestValues[name]!.toFixed(4) : '--'}
            </div>
          </div>
        ))}
      </div>

      {/* Loss chart */}
      {lossChartData.length > 0 && (
        <div style={{ flexShrink: 0 }}>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, letterSpacing: '0.08em' }}>
            LOSS
          </div>
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lossChartData}>
                <CartesianGrid stroke={T.surface3} strokeDasharray="3 3" />
                <XAxis
                  dataKey="step"
                  stroke={T.dim}
                  tick={{ fontFamily: F, fontSize: FS.xxs, fill: T.dim }}
                />
                <YAxis
                  stroke={T.dim}
                  tick={{ fontFamily: F, fontSize: FS.xxs, fill: T.dim }}
                  width={50}
                />
                <Tooltip content={<CustomTooltip />} />
                {lossMetrics.map((name, i) => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={CHART_COLORS[i % CHART_COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Learning rate chart */}
      {lrMetrics.length > 0 && (
        <div style={{ flexShrink: 0 }}>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, letterSpacing: '0.08em' }}>
            LEARNING RATE
          </div>
          <div style={{ height: 120 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={lrMetrics.flatMap((name) =>
                  (allSeries[name] || []).map((p) => ({ step: p.step, [name]: p.value }))
                )}
              >
                <CartesianGrid stroke={T.surface3} strokeDasharray="3 3" />
                <XAxis dataKey="step" stroke={T.dim} tick={{ fontFamily: F, fontSize: FS.xxs, fill: T.dim }} />
                <YAxis stroke={T.dim} tick={{ fontFamily: F, fontSize: FS.xxs, fill: T.dim }} width={60} />
                <Tooltip content={<CustomTooltip />} />
                {lrMetrics.map((name, i) => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={CHART_COLORS[(i + 3) % CHART_COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Other metrics */}
      {otherMetrics.length > 0 && (
        <div style={{ flexShrink: 0 }}>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, letterSpacing: '0.08em' }}>
            OTHER METRICS
          </div>
          <div style={{ height: 150 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={(() => {
                  const allSteps = new Set<number>()
                  otherMetrics.forEach((name) => {
                    (allSeries[name] || []).forEach((p) => allSteps.add(p.step))
                  })
                  const steps = [...allSteps].sort((a, b) => a - b)
                  return steps.map((step) => {
                    const point: Record<string, any> = { step }
                    otherMetrics.forEach((name) => {
                      const match = (allSeries[name] || []).find((p) => p.step === step)
                      point[name] = match ? match.value : undefined
                    })
                    return point
                  })
                })()}
              >
                <CartesianGrid stroke={T.surface3} strokeDasharray="3 3" />
                <XAxis dataKey="step" stroke={T.dim} tick={{ fontFamily: F, fontSize: FS.xxs, fill: T.dim }} />
                <YAxis stroke={T.dim} tick={{ fontFamily: F, fontSize: FS.xxs, fill: T.dim }} width={50} />
                <Tooltip content={<CustomTooltip />} />
                {otherMetrics.map((name, i) => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={CHART_COLORS[(i + 5) % CHART_COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
