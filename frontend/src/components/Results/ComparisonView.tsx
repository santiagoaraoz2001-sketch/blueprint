import { useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import type { RunRow } from './ResultsTable'
import { Trophy, AlertTriangle } from 'lucide-react'

/** Metrics matching this pattern are lower-is-better (loss, error, latency, etc.) */
const LOWER_IS_BETTER = /loss|error|perplexity|latency|time|cost|miss|fail|cer|wer|mae|mse|rmse/i

interface ComparisonViewProps {
  runs: RunRow[]
}

function formatDuration(secs: number | null): string {
  if (secs == null) return '--'
  if (secs < 60) return `${secs.toFixed(1)}s`
  const m = Math.floor(secs / 60)
  const s = Math.round(secs % 60)
  return `${m}m ${s}s`
}

export default function ComparisonView({ runs }: ComparisonViewProps) {
  if (runs.length < 2) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
          Select 2-4 runs from the table to compare
        </span>
      </div>
    )
  }

  // Collect all metric keys from all runs
  const metricKeys = useMemo(() => {
    const keys = new Set<string>()
    runs.forEach((r) => {
      if (r.metrics) Object.keys(r.metrics).forEach((k) => keys.add(k))
    })
    return Array.from(keys)
  }, [runs])

  // Collect all config keys across all nodes
  const configKeys = useMemo(() => {
    const keys = new Set<string>()
    runs.forEach((r) => {
      const nodes = r.config_snapshot?.nodes || []
      nodes.forEach((n: any) => {
        const cfg = n?.data?.config || {}
        Object.keys(cfg).forEach((k) => keys.add(k))
      })
    })
    return Array.from(keys)
  }, [runs])

  const getConfigValue = (run: RunRow, key: string): string => {
    const nodes = run.config_snapshot?.nodes || []
    for (const n of nodes) {
      const cfg = n?.data?.config || {}
      if (key in cfg) return String(cfg[key])
    }
    return '--'
  }

  /** For a metric row, determine best and worst index given numeric values.
   *  Metrics containing "loss", "error", "perplexity", "latency", "time", "cost"
   *  are lower-is-better; all others are higher-is-better. */
  const getBestWorst = (values: (number | null | undefined)[], metricName: string): { bestIdx: number; worstIdx: number } => {
    const lowerBetter = LOWER_IS_BETTER.test(metricName)

    let bestIdx = -1
    let worstIdx = -1
    let best = lowerBetter ? Infinity : -Infinity
    let worst = lowerBetter ? -Infinity : Infinity

    values.forEach((v, i) => {
      if (typeof v === 'number') {
        const isBetter = lowerBetter ? v < best : v > best
        const isWorse = lowerBetter ? v > worst : v < worst
        if (isBetter) { best = v; bestIdx = i }
        if (isWorse) { worst = v; worstIdx = i }
      }
    })
    // If all same value, no highlighting
    if (bestIdx === worstIdx) return { bestIdx: -1, worstIdx: -1 }
    return { bestIdx, worstIdx }
  }

  const cellBase: React.CSSProperties = {
    padding: '5px 10px',
    borderBottom: `1px solid ${T.border}`,
    fontFamily: F,
    fontSize: FS.sm,
    color: T.sec,
    textAlign: 'left',
  }

  const headerCell: React.CSSProperties = {
    ...cellBase,
    color: T.dim,
    fontSize: FS.xxs,
    fontWeight: 700,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    background: T.surface2,
  }

  const labelCell: React.CSSProperties = {
    ...cellBase,
    color: T.dim,
    fontWeight: 600,
    minWidth: 120,
  }

  const sectionHeaderStyle: React.CSSProperties = {
    ...headerCell,
    background: T.surface1,
    padding: '8px 10px 4px',
  }

  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={headerCell}>METRIC</th>
            {runs.map((r, i) => (
              <th key={r.id} style={headerCell}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  RUN {i + 1}
                </div>
                <div style={{ fontSize: FS.xxs, color: T.dim, fontWeight: 400, marginTop: 2 }}>
                  {r.id.slice(0, 8)}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* Status row */}
          <tr>
            <td style={labelCell}>Status</td>
            {runs.map((r) => (
              <td key={r.id} style={cellBase}>
                <span
                  style={{
                    color: r.status === 'complete' ? T.green : r.status === 'failed' ? T.red : T.amber,
                    fontWeight: 600,
                  }}
                >
                  {r.status.toUpperCase()}
                </span>
              </td>
            ))}
          </tr>

          {/* Duration row */}
          <tr>
            <td style={labelCell}>Duration</td>
            {runs.map((r) => (
              <td key={r.id} style={cellBase}>
                {formatDuration(r.duration_seconds)}
              </td>
            ))}
          </tr>

          {/* Metrics section header */}
          {metricKeys.length > 0 && (
            <tr>
              <td colSpan={runs.length + 1} style={sectionHeaderStyle}>
                METRICS
              </td>
            </tr>
          )}

          {/* Metric rows with best/worst highlighting */}
          {metricKeys.map((key) => {
            const values = runs.map((r) => r.metrics?.[key])
            const numericValues = values.map((v) => (typeof v === 'number' ? v : null))
            const { bestIdx, worstIdx } = getBestWorst(numericValues, key)

            return (
              <tr key={key}>
                <td style={labelCell}>{key}</td>
                {runs.map((r, i) => {
                  const v = r.metrics?.[key]
                  const isNum = typeof v === 'number'
                  const isBest = i === bestIdx
                  const isWorst = i === worstIdx

                  return (
                    <td
                      key={r.id}
                      style={{
                        ...cellBase,
                        color: isBest ? T.green : isWorst ? T.red : T.sec,
                        fontWeight: isBest || isWorst ? 700 : 400,
                        background: isBest
                          ? `${T.green}08`
                          : isWorst
                            ? `${T.red}08`
                            : 'transparent',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        {isBest && <Trophy size={8} color={T.green} />}
                        {isWorst && <AlertTriangle size={8} color={T.red} />}
                        <span>
                          {v == null ? '--' : isNum ? v.toFixed(4) : String(v)}
                        </span>
                      </div>
                    </td>
                  )
                })}
              </tr>
            )
          })}

          {/* Config diff section */}
          {configKeys.length > 0 && (
            <tr>
              <td colSpan={runs.length + 1} style={sectionHeaderStyle}>
                CONFIG DIFF
              </td>
            </tr>
          )}

          {configKeys.map((key) => {
            const values = runs.map((r) => getConfigValue(r, key))
            const allSame = values.every((v) => v === values[0])

            return (
              <tr key={`cfg_${key}`}>
                <td style={labelCell}>{key}</td>
                {runs.map((r, i) => (
                  <td
                    key={r.id}
                    style={{
                      ...cellBase,
                      color: allSame ? T.dim : T.amber,
                      fontWeight: allSame ? 400 : 600,
                      background: allSame ? 'transparent' : `${T.amber}08`,
                    }}
                  >
                    {values[i]}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
