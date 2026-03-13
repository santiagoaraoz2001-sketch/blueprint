import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import AutoLineChart from './AutoLineChart'
import ProgressBar from '@/components/shared/ProgressBar'
import { Eye, EyeOff } from 'lucide-react'

interface Props { runId: string; blockId: string }

export default function DataDashboard({ runId, blockId }: Props) {
  const [showRaw, setShowRaw] = useState(false)
  const block = useMetricsStore((s) => s.runs[runId]?.blocks[blockId])
  if (!block) return null

  const metrics = block.metrics
  const nullCount = metrics['data/null_count'] || []
  const dupCount = metrics['data/duplicate_count'] || []
  const errorRows = metrics['data/error_rows'] || []
  const metricNames = Object.keys(metrics).filter((n) => n !== '__started')

  const allEvents = Object.entries(metrics).flatMap(([name, points]) =>
    points.map((p) => ({ name, ...p }))
  ).sort((a, b) => a.timestamp - b.timestamp)

  const latestNull = nullCount.length > 0 ? nullCount[nullCount.length - 1].value : null
  const latestDup = dupCount.length > 0 ? dupCount[dupCount.length - 1].value : null
  const latestErr = errorRows.length > 0 ? errorRows[errorRows.length - 1].value : null

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.text, fontWeight: 700 }}>
          Data Dashboard
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
      ) : (
        <>
          <div style={{ marginBottom: 16 }}>
            <ProgressBar value={block.progress * 100} showLabel />
          </div>

          {/* Data quality summary */}
          {(latestNull != null || latestDup != null || latestErr != null) && (
            <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
              {latestNull != null && (
                <div style={{ flex: 1, padding: 10, background: T.surface1, border: `1px solid ${T.border}` }}>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>NULL VALUES</div>
                  <div style={{ fontFamily: F, fontSize: FS.lg, color: latestNull > 0 ? T.amber : T.green, fontWeight: 700 }}>
                    {latestNull}
                  </div>
                </div>
              )}
              {latestDup != null && (
                <div style={{ flex: 1, padding: 10, background: T.surface1, border: `1px solid ${T.border}` }}>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>DUPLICATES</div>
                  <div style={{ fontFamily: F, fontSize: FS.lg, color: latestDup > 0 ? T.amber : T.green, fontWeight: 700 }}>
                    {latestDup}
                  </div>
                </div>
              )}
              {latestErr != null && (
                <div style={{ flex: 1, padding: 10, background: T.surface1, border: `1px solid ${T.border}` }}>
                  <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>ERROR ROWS</div>
                  <div style={{ fontFamily: F, fontSize: FS.lg, color: latestErr > 0 ? T.red : T.green, fontWeight: 700 }}>
                    {latestErr}
                  </div>
                </div>
              )}
            </div>
          )}

          {metricNames.filter((n) => !n.startsWith('data/')).map((name) => (
            <div key={name} style={{ marginBottom: 16 }}>
              <AutoLineChart data={metrics[name]} color={T.cyan} height={180} label={name} />
            </div>
          ))}

          {metricNames.length === 0 && (
            <div style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, textAlign: 'center', padding: 40, animation: 'pulse 2s ease-in-out infinite' }}>
              Waiting for data processing metrics...
            </div>
          )}
        </>
      )}
    </div>
  )
}
