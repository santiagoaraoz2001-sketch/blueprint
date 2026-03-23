import { useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, type MetricPoint } from '@/stores/metricsStore'
import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface DefaultDashboardProps {
  runId: string
  blockId: string
}

const CHART_COLORS = ['#4af6c3', '#3B82F6', '#f59e0b', '#8B5CF6', '#EC4899', '#22c55e']

function MiniChart({ series, color }: { series: MetricPoint[]; color: string }) {
  if (series.length < 2) return null
  const data = series.map((p) => ({ step: p.step, value: p.value }))
  return (
    <div style={{ height: 40, width: 100 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function DefaultDashboard({ runId, blockId }: DefaultDashboardProps) {
  const blockMetrics = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.metrics)
  const block = useMetricsStore((s) => s.runs[runId]?.blocks[blockId])

  const allMetricNames = useMemo(() => blockMetrics ? Object.keys(blockMetrics) : [], [blockMetrics])

  const categorized = useMemo(() => {
    const lossLike = allMetricNames.filter((n) => n.toLowerCase().includes('loss'))
    const accLike = allMetricNames.filter(
      (n) => n.toLowerCase().includes('acc') || n.toLowerCase().includes('accuracy')
    )
    const others = allMetricNames.filter((n) => !lossLike.includes(n) && !accLike.includes(n))

    const getSeries = (name: string): MetricPoint[] => blockMetrics?.[name] || []

    return { lossLike, accLike, others, getSeries }
  }, [allMetricNames, blockMetrics])

  if (allMetricNames.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          gap: 8,
        }}
      >
        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>
          {block?.status === 'running' ? 'Waiting for metrics...' : 'No metrics recorded'}
        </div>
        {block && (
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            Block: {block.label} ({block.status})
          </div>
        )}
        {block?.status === 'running' && block.progress > 0 && (
          <div style={{ width: 120, height: 4, background: T.surface3, overflow: 'hidden' }}>
            <div
              style={{
                width: `${Math.round(block.progress * 100)}%`,
                height: '100%',
                background: T.cyan,
                transition: 'width 0.3s ease',
              }}
            />
          </div>
        )}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', padding: '8px 12px', gap: 16 }}>
      <div style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700 }}>
        {block?.label || blockId}
      </div>

      {/* Progress */}
      {block?.status === 'running' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ flex: 1, height: 4, background: T.surface3, overflow: 'hidden' }}>
            <div style={{ width: `${Math.round((block.progress || 0) * 100)}%`, height: '100%', background: T.cyan, transition: 'width 0.3s ease' }} />
          </div>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{Math.round((block.progress || 0) * 100)}%</span>
        </div>
      )}

      {/* All metrics as key-value or sparkline */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        {allMetricNames.map((name, i) => {
          const series = categorized.getSeries(name)
          const latest = series.length > 0 ? series[series.length - 1].value : null

          return (
            <div
              key={name}
              style={{
                padding: '8px 10px',
                background: T.surface1,
                border: `1px solid ${T.border}`,
                minWidth: 120,
                flex: '1 0 120px',
                maxWidth: 220,
              }}
            >
              <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 4 }}>{name}</div>
              <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700 }}>
                {latest != null ? (Math.abs(latest) < 0.01 || Math.abs(latest) > 9999 ? latest.toExponential(3) : latest.toFixed(4)) : '--'}
              </div>
              {series.length > 5 && (
                <div style={{ marginTop: 4 }}>
                  <MiniChart series={series} color={CHART_COLORS[i % CHART_COLORS.length]} />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
