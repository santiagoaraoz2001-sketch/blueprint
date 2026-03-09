import { T, F, FS } from '@/lib/design-tokens'
import type { RunRow } from './ResultsTable'
import { ArrowUp, ArrowDown, Minus } from 'lucide-react'

interface RunComparisonProps {
  runs: RunRow[]
}

function formatDuration(secs: number | null): string {
  if (secs == null) return '—'
  if (secs < 60) return `${secs.toFixed(1)}s`
  const m = Math.floor(secs / 60)
  const s = Math.round(secs % 60)
  return `${m}m ${s}s`
}

function DeltaArrow({ a, b }: { a: number | null; b: number | null }) {
  if (a == null || b == null) return <Minus size={8} color={T.dim} />
  const diff = b - a
  if (Math.abs(diff) < 0.0001) return <Minus size={8} color={T.dim} />
  if (diff > 0) return <ArrowUp size={8} color={T.green} />
  return <ArrowDown size={8} color={T.red} />
}

export default function RunComparison({ runs }: RunComparisonProps) {
  if (runs.length < 2) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
          Select 2-4 runs from the table to compare
        </span>
      </div>
    )
  }

  // Collect all metric keys
  const metricKeys = new Set<string>()
  runs.forEach((r) => {
    if (r.metrics) Object.keys(r.metrics).forEach((k) => metricKeys.add(k))
  })

  // Collect all config keys
  const configKeys = new Set<string>()
  runs.forEach((r) => {
    const nodes = r.config_snapshot?.nodes || []
    nodes.forEach((n: any) => {
      const cfg = n?.data?.config || {}
      Object.keys(cfg).forEach((k) => configKeys.add(k))
    })
  })

  const getConfigValue = (run: RunRow, key: string): string => {
    const nodes = run.config_snapshot?.nodes || []
    for (const n of nodes) {
      const cfg = n?.data?.config || {}
      if (key in cfg) return String(cfg[key])
    }
    return '—'
  }

  const cellStyle: React.CSSProperties = {
    padding: '5px 10px',
    borderBottom: `1px solid ${T.border}`,
    fontFamily: F,
    fontSize: FS.sm,
    color: T.sec,
  }

  const headerCellStyle: React.CSSProperties = {
    ...cellStyle,
    color: T.dim,
    fontSize: FS.xxs,
    fontWeight: 600,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    background: T.surface2,
  }

  const labelCellStyle: React.CSSProperties = {
    ...cellStyle,
    color: T.dim,
    fontWeight: 600,
    minWidth: 120,
  }

  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={headerCellStyle}>METRIC</th>
            {runs.map((r, i) => (
              <th key={r.id} style={headerCellStyle}>
                RUN {i + 1}
                <div style={{ fontSize: FS.xxs, color: T.dim, fontWeight: 400, marginTop: 2 }}>
                  {r.id.slice(0, 8)}
                </div>
              </th>
            ))}
            {runs.length >= 2 && <th style={headerCellStyle}>DELTA</th>}
          </tr>
        </thead>
        <tbody>
          {/* Status row */}
          <tr>
            <td style={labelCellStyle}>Status</td>
            {runs.map((r) => (
              <td key={r.id} style={cellStyle}>
                <span
                  style={{
                    color: r.status === 'complete' ? T.green : r.status === 'failed' ? T.red : T.amber,
                  }}
                >
                  {r.status}
                </span>
              </td>
            ))}
            {runs.length >= 2 && <td style={cellStyle} />}
          </tr>

          {/* Duration row */}
          <tr>
            <td style={labelCellStyle}>Duration</td>
            {runs.map((r) => (
              <td key={r.id} style={cellStyle}>
                {formatDuration(r.duration_seconds)}
              </td>
            ))}
            {runs.length >= 2 && (
              <td style={cellStyle}>
                <DeltaArrow
                  a={runs[0].duration_seconds}
                  b={runs[runs.length - 1].duration_seconds}
                />
              </td>
            )}
          </tr>

          {/* Metric rows */}
          {Array.from(metricKeys).map((key) => {
            const values = runs.map((r) => r.metrics?.[key])
            const numericValues = values.filter((v): v is number => typeof v === 'number')

            return (
              <tr key={key}>
                <td style={labelCellStyle}>{key}</td>
                {runs.map((r) => {
                  const v = r.metrics?.[key]
                  const isNum = typeof v === 'number'
                  // Highlight best value
                  const isBest =
                    isNum && numericValues.length > 1 && v === Math.max(...numericValues)
                  return (
                    <td
                      key={r.id}
                      style={{
                        ...cellStyle,
                        color: isBest ? T.cyan : T.sec,
                        fontWeight: isBest ? 600 : 400,
                      }}
                    >
                      {v == null ? '—' : isNum ? v.toFixed(4) : String(v)}
                    </td>
                  )
                })}
                {runs.length >= 2 && (
                  <td style={cellStyle}>
                    {typeof values[0] === 'number' && typeof values[values.length - 1] === 'number' ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <DeltaArrow a={values[0] as number} b={values[values.length - 1] as number} />
                        <span
                          style={{
                            fontSize: FS.xxs,
                            color:
                              (values[values.length - 1] as number) > (values[0] as number) ? T.green : T.red,
                          }}
                        >
                          {((values[values.length - 1] as number) - (values[0] as number)).toFixed(4)}
                        </span>
                      </div>
                    ) : null}
                  </td>
                )}
              </tr>
            )
          })}

          {/* Config diff rows */}
          {Array.from(configKeys).length > 0 && (
            <tr>
              <td
                colSpan={runs.length + 2}
                style={{
                  ...headerCellStyle,
                  background: T.surface1,
                  padding: '8px 10px 4px',
                }}
              >
                CONFIG
              </td>
            </tr>
          )}
          {Array.from(configKeys).map((key) => {
            const values = runs.map((r) => getConfigValue(r, key))
            const allSame = values.every((v) => v === values[0])
            return (
              <tr key={`config_${key}`}>
                <td style={labelCellStyle}>{key}</td>
                {runs.map((r, i) => (
                  <td
                    key={r.id}
                    style={{
                      ...cellStyle,
                      color: allSame ? T.dim : T.amber,
                    }}
                  >
                    {values[i]}
                  </td>
                ))}
                {runs.length >= 2 && (
                  <td style={cellStyle}>
                    {!allSame && (
                      <span style={{ fontSize: FS.xxs, color: T.amber }}>DIFFERS</span>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
