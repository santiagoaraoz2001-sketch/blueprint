import { useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, EMPTY_BLOCK_METRICS, type MetricSeries } from '@/stores/metricsStore'
import AutoLineChart from './AutoLineChart'
import RawDataToggle from './RawDataToggle'
import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface Props { blockId: string }

/** Tiny inline sparkline for metrics with few data points */
function Sparkline({ series, color }: { series: MetricSeries[]; color: string }) {
  const data = series.map((s, i) => ({ i, v: s.value }))
  return (
    <div style={{ width: 80, height: 24 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function DefaultDashboard({ blockId }: Props) {
  const blockMetrics = useMetricsStore((s) => s.metrics[blockId] ?? EMPTY_BLOCK_METRICS)
  const block = useMetricsStore((s) => s.monitorExecutionOrder.find(b => b.id === blockId))
  const allLogs = useMetricsStore((s) => s.logs)
  const logs = useMemo(() => allLogs.filter(l => l.blockId === blockId).slice(-10), [allLogs, blockId])

  const metricCategories = useMemo(() => {
    const charts: { name: string; type: 'descending' | 'ascending' | 'sparkline' | 'value' }[] = []

    for (const [name, series] of Object.entries(blockMetrics)) {
      const nameLower = name.toLowerCase()
      if (nameLower.includes('loss') && series.length > 5) {
        charts.push({ name, type: 'descending' })
      } else if ((nameLower.includes('acc') || nameLower.includes('accuracy')) && series.length > 5) {
        charts.push({ name, type: 'ascending' })
      } else if (series.length > 5) {
        charts.push({ name, type: 'sparkline' })
      } else {
        charts.push({ name, type: 'value' })
      }
    }

    return charts
  }, [blockMetrics])

  const hasMetrics = metricCategories.length > 0

  return (
    <RawDataToggle blockId={blockId}>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Block progress */}
        {block && (
          <div style={{
            display: 'flex', gap: 12, padding: '8px 12px',
            background: T.surface1, border: `1px solid ${T.border}`,
            alignItems: 'center',
          }}>
            <div>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Block</span>
              <div style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>{block.name}</div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{
                width: '100%', height: 4, background: T.surface3, borderRadius: 2,
                overflow: 'hidden',
              }}>
                <div style={{
                  width: `${Math.round(block.progress * 100)}%`,
                  height: '100%', background: T.cyan,
                  transition: 'width 0.3s ease',
                }} />
              </div>
            </div>
            <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, fontVariantNumeric: 'tabular-nums' }}>
              {Math.round(block.progress * 100)}%
            </span>
          </div>
        )}

        {/* Line charts for metrics with enough data */}
        {metricCategories.filter(m => m.type === 'descending' || m.type === 'ascending').map(m => (
          <AutoLineChart
            key={m.name}
            metricName={m.name}
            blockId={blockId}
            color={m.type === 'descending' ? '#00BFA5' : '#3B82F6'}
            height={180}
            title={m.name.toUpperCase()}
          />
        ))}

        {/* Sparkline metrics */}
        {metricCategories.filter(m => m.type === 'sparkline').length > 0 && (
          <div style={{
            background: T.surface1, border: `1px solid ${T.border}`, padding: 8,
          }}>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
              color: T.dim, letterSpacing: '0.06em', marginBottom: 8,
            }}>
              METRICS
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              {metricCategories.filter(m => m.type === 'sparkline').map(m => {
                const series = blockMetrics[m.name] || []
                const latest = series.length > 0 ? series[series.length - 1].value : null
                return (
                  <div key={m.name} style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '4px 8px', background: T.surface2,
                    border: `1px solid ${T.border}`,
                  }}>
                    <div>
                      <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{m.name}</div>
                      <div style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                        {latest !== null ? latest.toLocaleString(undefined, { maximumFractionDigits: 4 }) : '—'}
                      </div>
                    </div>
                    <Sparkline series={series} color="#00BFA5" />
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Key-value display for metrics with few data points */}
        {metricCategories.filter(m => m.type === 'value').length > 0 && (
          <div style={{
            background: T.surface1, border: `1px solid ${T.border}`, padding: 8,
          }}>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
              color: T.dim, letterSpacing: '0.06em', marginBottom: 8,
            }}>
              VALUES
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {metricCategories.filter(m => m.type === 'value').map(m => {
                const series = blockMetrics[m.name] || []
                const latest = series.length > 0 ? series[series.length - 1].value : null
                return (
                  <div key={m.name} style={{
                    padding: '4px 8px', background: T.surface2,
                    border: `1px solid ${T.border}`,
                  }}>
                    <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{m.name}</div>
                    <div style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                      {latest !== null ? latest.toLocaleString(undefined, { maximumFractionDigits: 6 }) : '—'}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Mini log stream */}
        {logs.length > 0 && (
          <div style={{
            background: T.surface1, border: `1px solid ${T.border}`, padding: 8,
            maxHeight: 120, overflow: 'auto',
          }}>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
              color: T.dim, letterSpacing: '0.06em', marginBottom: 4,
            }}>
              RECENT LOGS
            </div>
            {logs.map((log, i) => (
              <div key={i} style={{
                fontFamily: F, fontSize: FS.xxs, color: log.level === 'error' ? T.red : T.dim,
                padding: '1px 0', lineHeight: 1.4,
              }}>
                <span style={{ color: T.dim }}>[{log.timestamp}]</span> {log.message}
              </div>
            ))}
          </div>
        )}

        {/* Never blank */}
        {!hasMetrics && !block && (
          <div style={{
            padding: 24, textAlign: 'center',
            fontFamily: F, fontSize: FS.xs, color: T.dim,
          }}>
            Waiting for metrics...
          </div>
        )}
      </div>
    </RawDataToggle>
  )
}
