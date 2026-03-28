import { useState, useEffect, useMemo, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { api } from '@/api/client'
import { Trophy, FileDown, BarChart3 } from 'lucide-react'
import TraceabilityPanel from './TraceabilityPanel'
import toast from 'react-hot-toast'

interface ComparisonMatrixProps {
  runIds: string[]
  projectId?: string
  onPinBest?: (runId: string) => void
}

interface ComparisonData {
  config_columns: string[]
  metric_columns: string[]
  runs: ComparisonRow[]
}

interface ComparisonRow {
  id: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  error_message: string | null
  config: Record<string, any>
  metrics: Record<string, any>
  metric_sources: Record<string, string>  // metric_key -> node_id
  best_in_project?: boolean
}

export default function ComparisonMatrix({ runIds, projectId, onPinBest }: ComparisonMatrixProps) {
  const [data, setData] = useState<ComparisonData | null>(null)
  const [loading, setLoading] = useState(true)
  const [traceTarget, setTraceTarget] = useState<{ runId: string; nodeId: string; metricName: string } | null>(null)
  const [pinnedRunId, setPinnedRunId] = useState<string | null>(null)

  useEffect(() => {
    if (!runIds.length) return
    setLoading(true)
    const ids = runIds.join(',')
    api
      .get<ComparisonData>(`/runs/compare?ids=${ids}`)
      .then((d) => {
        setData(d)
        // Check which run is pinned
        const bestRun = d.runs.find((r: any) => r.best_in_project)
        if (bestRun) setPinnedRunId(bestRun.id)
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [runIds])

  // Find best value per metric (for highlighting)
  const bestMetrics = useMemo(() => {
    if (!data) return {}
    const best: Record<string, { value: number; runId: string }> = {}
    for (const mk of data.metric_columns) {
      let bestVal: number | null = null
      let bestId = ''
      const isLowerBetter = mk.toLowerCase().includes('loss') || mk.toLowerCase().includes('error')
      for (const row of data.runs) {
        const val = row.metrics[mk]
        if (typeof val !== 'number') continue
        if (bestVal === null || (isLowerBetter ? val < bestVal : val > bestVal)) {
          bestVal = val
          bestId = row.id
        }
      }
      if (bestVal !== null) {
        best[mk] = { value: bestVal, runId: bestId }
      }
    }
    return best
  }, [data])

  // Find which config values differ between runs
  const diffingConfigs = useMemo(() => {
    if (!data || data.runs.length < 2) return new Set<string>()
    const diffs = new Set<string>()
    for (const ck of data.config_columns) {
      const values = data.runs.map((r) => JSON.stringify(r.config[ck]))
      if (new Set(values).size > 1) diffs.add(ck)
    }
    return diffs
  }, [data])

  const handlePinBest = useCallback(async (runId: string) => {
    try {
      await api.post(`/runs/${runId}/pin-best`)
      setPinnedRunId(runId)
      onPinBest?.(runId)
      toast.success('Run pinned as best')
    } catch {
      toast.error('Failed to pin run')
    }
  }, [onPinBest])

  const handleCellClick = useCallback((runId: string, metricName: string) => {
    if (!data) return

    // Look up the exact node_id that produced this metric from the
    // metric_sources mapping returned by the compare endpoint. This mapping
    // is built from the run's metrics_log which records node_id on every
    // metric event emitted during execution.
    const row = data.runs.find((r) => r.id === runId)
    if (!row) return

    const nodeId = row.metric_sources?.[metricName]
    if (nodeId) {
      setTraceTarget({ runId, nodeId, metricName })
      return
    }

    // Fallback for legacy runs that lack metrics_log: scan nodes in the
    // config_snapshot and find a node whose block_type appears as the prefix
    // of the metric key (e.g. "evaluation.accuracy" -> block_type "evaluation").
    const dotIdx = metricName.indexOf('.')
    const blockTypePrefix = dotIdx > 0 ? metricName.slice(0, dotIdx) : null

    api
      .get<any>(`/runs/${runId}`)
      .then((run) => {
        const nodes: any[] = run.config_snapshot?.nodes || []
        let matched: any = null

        if (blockTypePrefix) {
          matched = nodes.find(
            (n: any) => n.data?.type === blockTypePrefix
          )
        }

        // Final fallback: last node in pipeline
        if (!matched) {
          matched = nodes[nodes.length - 1]
        }

        if (matched) {
          setTraceTarget({ runId, nodeId: matched.id, metricName })
        }
      })
      .catch(() => {})
  }, [data])

  if (loading) {
    return (
      <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center', padding: 20 }}>
        Loading comparison data...
      </div>
    )
  }

  if (!data || data.runs.length === 0) {
    return (
      <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center', padding: 20 }}>
        No runs to compare
      </div>
    )
  }

  // Only show differing config columns to reduce noise
  const visibleConfigs = data.config_columns.filter((c) => diffingConfigs.has(c))

  return (
    <div style={{ position: 'relative' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
      }}>
        <BarChart3 size={13} color={T.cyan} />
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700 }}>
          Comparison Matrix
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          Click any metric to trace provenance
        </span>
      </div>

      <div style={{ overflow: 'auto', maxHeight: 400 }}>
        <table style={{
          width: '100%', borderCollapse: 'collapse',
          fontFamily: F, fontSize: FS.xxs,
        }}>
          <thead>
            <tr>
              <th style={thStyle}>Run</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Duration</th>
              {visibleConfigs.map((ck) => (
                <th key={ck} style={{ ...thStyle, color: T.amber }}>
                  {ck.split('.').pop()}
                </th>
              ))}
              {data.metric_columns.map((mk) => (
                <th key={mk} style={{ ...thStyle, color: T.cyan }}>
                  {mk}
                </th>
              ))}
              <th style={thStyle}>Pin</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((row) => {
              const isPinned = pinnedRunId === row.id
              return (
                <tr
                  key={row.id}
                  style={{
                    borderBottom: `1px solid ${T.surface3}`,
                    background: isPinned ? `${T.amber}06` : 'transparent',
                  }}
                >
                  <td style={{
                    ...tdStyle,
                    fontWeight: 600,
                    borderLeft: isPinned ? `2px solid ${T.amber}` : '2px solid transparent',
                  }}>
                    {row.id.slice(0, 8)}
                  </td>
                  <td style={{
                    ...tdStyle,
                    color: row.status === 'complete' ? T.green : row.status === 'failed' ? T.red : T.dim,
                  }}>
                    {row.status}
                  </td>
                  <td style={tdStyle}>
                    {row.duration_seconds != null
                      ? row.duration_seconds >= 60
                        ? `${(row.duration_seconds / 60).toFixed(1)}m`
                        : `${row.duration_seconds.toFixed(1)}s`
                      : '-'}
                  </td>
                  {visibleConfigs.map((ck) => (
                    <td key={ck} style={{ ...tdStyle, color: T.sec }}>
                      {row.config[ck] != null ? String(row.config[ck]).slice(0, 20) : '-'}
                    </td>
                  ))}
                  {data.metric_columns.map((mk) => {
                    const val = row.metrics[mk]
                    const isBest = bestMetrics[mk]?.runId === row.id
                    return (
                      <td
                        key={mk}
                        onClick={() => handleCellClick(row.id, mk)}
                        style={{
                          ...tdStyle,
                          cursor: 'pointer',
                          color: isBest ? T.cyan : T.text,
                          fontWeight: isBest ? 700 : 400,
                          background: isBest ? `${T.cyan}08` : 'transparent',
                        }}
                        title="Click to trace provenance"
                      >
                        {val != null
                          ? typeof val === 'number'
                            ? val.toFixed(6)
                            : String(val)
                          : '-'}
                      </td>
                    )
                  })}
                  <td style={tdStyle}>
                    <button
                      onClick={() => handlePinBest(row.id)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        padding: 2,
                      }}
                      title={isPinned ? 'Currently pinned' : 'Pin as best'}
                    >
                      <Trophy
                        size={12}
                        color={isPinned ? T.amber : T.dim}
                        fill={isPinned ? T.amber : 'none'}
                      />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Traceability panel */}
      {traceTarget && (
        <TraceabilityPanel
          runId={traceTarget.runId}
          nodeId={traceTarget.nodeId}
          metricName={traceTarget.metricName}
          onClose={() => setTraceTarget(null)}
        />
      )}
    </div>
  )
}

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '6px 8px',
  color: T.dim,
  fontWeight: 600,
  fontSize: 10,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  borderBottom: `1px solid ${T.border}`,
  whiteSpace: 'nowrap',
  position: 'sticky',
  top: 0,
  background: T.bg,
}

const tdStyle: React.CSSProperties = {
  padding: '5px 8px',
  color: T.text,
  whiteSpace: 'nowrap',
}
