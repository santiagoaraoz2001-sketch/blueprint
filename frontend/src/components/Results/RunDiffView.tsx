import { T, F, FS } from '@/lib/design-tokens'
import { ArrowUp, ArrowDown, Minus } from 'lucide-react'

interface RunData {
  id: string
  status: string
  started_at: string | null
  duration_seconds: number | null
  config: Record<string, any>
  metrics: Record<string, any>
}

interface RunDiffViewProps {
  runA: RunData
  runB: RunData
  onClose: () => void
}

function computeDiff(runA: RunData, runB: RunData) {
  const configDiff: { key: string; valueA: any; valueB: any; changed: boolean }[] = []
  const allConfigKeys = new Set([...Object.keys(runA.config || {}), ...Object.keys(runB.config || {})])
  for (const key of [...allConfigKeys].sort()) {
    const a = runA.config?.[key]
    const b = runB.config?.[key]
    configDiff.push({ key, valueA: a, valueB: b, changed: JSON.stringify(a) !== JSON.stringify(b) })
  }

  const metricDiff: { key: string; valueA: any; valueB: any; delta: { absolute: number; percent: number } | null }[] = []
  const allMetricKeys = new Set([...Object.keys(runA.metrics || {}), ...Object.keys(runB.metrics || {})])
  for (const key of [...allMetricKeys].sort()) {
    const a = runA.metrics?.[key]
    const b = runB.metrics?.[key]
    const delta = (typeof a === 'number' && typeof b === 'number' && a !== 0)
      ? { absolute: b - a, percent: ((b - a) / Math.abs(a)) * 100 }
      : null
    metricDiff.push({ key, valueA: a, valueB: b, delta })
  }

  return { configDiff, metricDiff }
}

export default function RunDiffView({ runA, runB, onClose }: RunDiffViewProps) {
  const { configDiff, metricDiff } = computeDiff(runA, runB)
  const changedCount = configDiff.filter(d => d.changed).length

  return (
    <div style={{
      padding: 20,
      background: T.surface1,
      border: `1px solid ${T.border}`,
      borderRadius: 8,
      maxHeight: '80vh',
      overflow: 'auto',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700 }}>
            Run {runA.id.slice(0, 8)} vs {runB.id.slice(0, 8)}
          </div>
          <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, marginTop: 2 }}>
            {changedCount} config change{changedCount !== 1 ? 's' : ''}
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: T.surface3, border: `1px solid ${T.border}`, borderRadius: 4,
            color: T.sec, fontFamily: F, fontSize: FS.xs, padding: '4px 12px', cursor: 'pointer',
          }}
        >
          Close
        </button>
      </div>

      {/* Config Differences */}
      {configDiff.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
            fontWeight: 700, letterSpacing: '0.12em', marginBottom: 8,
            textTransform: 'uppercase',
          }}>
            CONFIG DIFFERENCES
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <DiffTh>Parameter</DiffTh>
                <DiffTh>Run A</DiffTh>
                <DiffTh>Run B</DiffTh>
              </tr>
            </thead>
            <tbody>
              {configDiff.map(({ key, valueA, valueB, changed }) => (
                <tr key={key}>
                  <td style={{
                    fontFamily: F, fontSize: FS.xs, color: changed ? T.text : T.dim,
                    fontWeight: changed ? 700 : 400, padding: '6px 8px',
                    borderBottom: `1px solid ${T.border}`,
                  }}>
                    {key} {changed && <span style={{ color: '#F59E0B', fontSize: '8px' }}>*</span>}
                  </td>
                  <td style={{
                    fontFamily: 'monospace', fontSize: FS.xxs,
                    color: changed ? T.sec : T.dim, padding: '6px 8px',
                    borderBottom: `1px solid ${T.border}`,
                    background: changed ? '#F59E0B08' : 'transparent',
                  }}>
                    {formatValue(valueA)}
                  </td>
                  <td style={{
                    fontFamily: 'monospace', fontSize: FS.xxs,
                    color: changed ? T.text : T.dim, padding: '6px 8px',
                    borderBottom: `1px solid ${T.border}`,
                    background: changed ? '#F59E0B08' : 'transparent',
                  }}>
                    {formatValue(valueB)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Metric Comparison */}
      {metricDiff.length > 0 && (
        <div>
          <div style={{
            fontFamily: F, fontSize: FS.xxs, color: T.dim,
            fontWeight: 700, letterSpacing: '0.12em', marginBottom: 8,
            textTransform: 'uppercase',
          }}>
            METRIC COMPARISON
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <DiffTh>Metric</DiffTh>
                <DiffTh>Run A</DiffTh>
                <DiffTh>Run B</DiffTh>
                <DiffTh>Delta</DiffTh>
              </tr>
            </thead>
            <tbody>
              {metricDiff.map(({ key, valueA, valueB, delta }) => {
                const isLossMetric = key.toLowerCase().includes('loss') || key.toLowerCase().includes('error') || key.toLowerCase().includes('perplexity')
                const improved = delta ? (isLossMetric ? delta.absolute < 0 : delta.absolute > 0) : false
                const worsened = delta ? (isLossMetric ? delta.absolute > 0 : delta.absolute < 0) : false

                return (
                  <tr key={key}>
                    <td style={{
                      fontFamily: F, fontSize: FS.xs, color: T.text,
                      fontWeight: 600, padding: '6px 8px',
                      borderBottom: `1px solid ${T.border}`,
                    }}>
                      {key}
                    </td>
                    <td style={{
                      fontFamily: 'monospace', fontSize: FS.xxs, color: T.sec,
                      padding: '6px 8px', borderBottom: `1px solid ${T.border}`,
                    }}>
                      {typeof valueA === 'number' ? valueA.toFixed(4) : String(valueA ?? '-')}
                    </td>
                    <td style={{
                      fontFamily: 'monospace', fontSize: FS.xxs, color: T.sec,
                      padding: '6px 8px', borderBottom: `1px solid ${T.border}`,
                    }}>
                      {typeof valueB === 'number' ? valueB.toFixed(4) : String(valueB ?? '-')}
                    </td>
                    <td style={{
                      fontFamily: 'monospace', fontSize: FS.xxs,
                      padding: '6px 8px', borderBottom: `1px solid ${T.border}`,
                      color: improved ? '#22C55E' : worsened ? '#EF4444' : T.dim,
                      fontWeight: 700,
                    }}>
                      {delta ? (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                          {improved ? <ArrowUp size={10} /> : worsened ? <ArrowDown size={10} /> : <Minus size={10} />}
                          {delta.absolute > 0 ? '+' : ''}{delta.absolute.toFixed(4)}
                          <span style={{ fontSize: '7px', opacity: 0.8, marginLeft: 2 }}>
                            ({delta.percent > 0 ? '+' : ''}{delta.percent.toFixed(1)}%)
                          </span>
                        </span>
                      ) : '-'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Duration comparison */}
      {runA.duration_seconds != null && runB.duration_seconds != null && (
        <div style={{
          marginTop: 16, padding: '8px 12px',
          background: T.surface0, border: `1px solid ${T.border}`, borderRadius: 4,
          fontFamily: F, fontSize: FS.xs, color: T.sec,
          display: 'flex', gap: 16,
        }}>
          <span>Duration A: {formatDuration(runA.duration_seconds)}</span>
          <span>Duration B: {formatDuration(runB.duration_seconds)}</span>
          <span style={{
            color: runB.duration_seconds < runA.duration_seconds ? '#22C55E' : '#F59E0B',
            fontWeight: 700,
          }}>
            {((runB.duration_seconds - runA.duration_seconds) / runA.duration_seconds * 100).toFixed(1)}%
          </span>
        </div>
      )}
    </div>
  )
}

function DiffTh({ children }: { children: React.ReactNode }) {
  return (
    <th style={{
      fontFamily: F, fontSize: FS.xxs, color: T.dim,
      fontWeight: 700, letterSpacing: '0.08em',
      textAlign: 'left', padding: '4px 8px',
      borderBottom: `1px solid ${T.border}`,
      textTransform: 'uppercase',
    }}>
      {children}
    </th>
  )
}

function formatValue(val: any): string {
  if (val === undefined || val === null) return '-'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const min = Math.floor(seconds / 60)
  const sec = Math.round(seconds % 60)
  return `${min}m ${sec}s`
}
