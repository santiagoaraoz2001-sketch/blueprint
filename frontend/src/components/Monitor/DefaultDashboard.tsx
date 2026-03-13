import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import AutoLineChart from './AutoLineChart'
import { Eye, EyeOff } from 'lucide-react'

interface Props { runId: string; blockId: string }

export default function DefaultDashboard({ runId, blockId }: Props) {
  const [showRaw, setShowRaw] = useState(false)
  const block = useMetricsStore((s) => s.runs[runId]?.blocks[blockId])
  if (!block) return null

  const metrics = block.metrics
  const metricNames = Object.keys(metrics).filter((n) => n !== '__started')

  const allEvents = Object.entries(metrics).flatMap(([name, points]) =>
    points.map((p) => ({ name, ...p }))
  ).sort((a, b) => a.timestamp - b.timestamp)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
          {block.label || 'Block'} Metrics
        </span>
        <button
          onClick={() => setShowRaw(!showRaw)}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 8px', background: showRaw ? `${T.cyan}14` : 'transparent',
            border: `1px solid ${showRaw ? T.cyan : T.border}`, color: showRaw ? T.cyan : T.dim,
            fontFamily: F, fontSize: FS.xxs, cursor: 'pointer',
          }}
        >
          {showRaw ? <EyeOff size={10} /> : <Eye size={10} />}
          {showRaw ? 'HIDE RAW' : 'RAW DATA'}
        </button>
      </div>

      {showRaw ? (
        <div style={{ overflow: 'auto', maxHeight: 500 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: F, fontSize: FS.xxs }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim }}>Step</th>
                <th style={{ padding: '4px 8px', textAlign: 'left', color: T.dim }}>Metric</th>
                <th style={{ padding: '4px 8px', textAlign: 'right', color: T.dim }}>Value</th>
                <th style={{ padding: '4px 8px', textAlign: 'right', color: T.dim }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {allEvents.map((e, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${T.surface4}` }}>
                  <td style={{ padding: '3px 8px', color: T.sec }}>{e.step ?? '—'}</td>
                  <td style={{ padding: '3px 8px', color: T.text }}>{e.name}</td>
                  <td style={{ padding: '3px 8px', color: T.cyan, textAlign: 'right' }}>{e.value.toFixed(6)}</td>
                  <td style={{ padding: '3px 8px', color: T.dim, textAlign: 'right' }}>{new Date(e.timestamp).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : metricNames.length > 0 ? (
        <>
          {metricNames.map((name) => {
            const data = metrics[name]
            const latest = data[data.length - 1]
            // For single-value metrics, show as number + sparkline
            if (data.length <= 2) {
              return (
                <div key={name} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '8px 12px', background: T.surface1, border: `1px solid ${T.border}`,
                  marginBottom: 8,
                }}>
                  <span style={{ fontFamily: F, fontSize: FS.xs, color: T.sec, flex: 1 }}>{name}</span>
                  <span style={{ fontFamily: F, fontSize: FS.md, color: T.cyan, fontWeight: 700 }}>
                    {latest?.value.toFixed(4)}
                  </span>
                </div>
              )
            }
            // For time-series, show as chart
            return (
              <div key={name} style={{ marginBottom: 16 }}>
                <AutoLineChart data={data} color={T.cyan} height={200} label={name} />
              </div>
            )
          })}
        </>
      ) : (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          height: 200, fontFamily: F, fontSize: FS.sm, color: T.dim,
        }}>
          <span style={{ animation: 'pulse 2s ease-in-out infinite' }}>
            Waiting for metrics...
          </span>
        </div>
      )}
    </div>
  )
}
