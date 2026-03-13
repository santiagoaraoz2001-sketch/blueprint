import { useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore } from '@/stores/metricsStore'
import { CheckCircle2, Loader, Clock } from 'lucide-react'

interface EvaluationDashboardProps {
  runId: string
  blockId: string
}

interface BenchmarkRow {
  name: string
  metric: string
  score: number | null
  complete: boolean
}

export default function EvaluationDashboard({ runId, blockId }: EvaluationDashboardProps) {
  const blockMetrics = useMetricsStore((s) => s.runs[runId]?.blocks[blockId]?.metrics)
  const block = useMetricsStore((s) => s.runs[runId]?.blocks[blockId])

  const allMetricNames = useMemo(() => blockMetrics ? Object.keys(blockMetrics) : [], [blockMetrics])

  const benchmarks = useMemo(() => {
    if (!blockMetrics) return []
    const benchmarkMetricNames = allMetricNames.filter((name) => name.startsWith('benchmark/'))
    const rows: BenchmarkRow[] = benchmarkMetricNames.map((name) => {
      const parts = name.split('/')
      const series = blockMetrics[name] || []
      const latest = series.length > 0 ? series[series.length - 1].value : null
      return {
        name: parts[1] || name,
        metric: parts[2] || 'score',
        score: latest,
        complete: latest !== null,
      }
    })

    // Also include non-benchmark metrics
    const otherMetricNames = allMetricNames.filter((name) => !name.startsWith('benchmark/'))
    otherMetricNames.forEach((name) => {
      const series = blockMetrics[name] || []
      const latest = series.length > 0 ? series[series.length - 1].value : null
      rows.push({
        name,
        metric: 'value',
        score: latest,
        complete: latest !== null,
      })
    })

    return rows
  }, [allMetricNames, blockMetrics])

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
        <Loader size={14} color={T.dim} style={{ marginRight: 8, animation: 'spin 1s linear infinite' }} />
        Waiting for evaluation results...
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'auto', padding: '8px 12px', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 700 }}>
          Evaluation — {block?.label || blockId}
        </span>
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
          {benchmarks.filter((b) => b.complete).length}/{benchmarks.length} complete
        </span>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.borderHi}` }}>
            <th style={{ padding: '6px 10px', textAlign: 'left', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 600, letterSpacing: '0.08em' }}>
              BENCHMARK
            </th>
            <th style={{ padding: '6px 10px', textAlign: 'left', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 600, letterSpacing: '0.08em' }}>
              METRIC
            </th>
            <th style={{ padding: '6px 10px', textAlign: 'right', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 600, letterSpacing: '0.08em' }}>
              SCORE
            </th>
            <th style={{ padding: '6px 10px', textAlign: 'center', fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 600 }}>
              STATUS
            </th>
          </tr>
        </thead>
        <tbody>
          {benchmarks.map((row, i) => (
            <tr
              key={i}
              style={{
                borderBottom: `1px solid ${T.border}`,
                background: row.complete ? 'transparent' : `${T.surface1}`,
              }}
            >
              <td style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 600 }}>
                {row.name}
              </td>
              <td style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                {row.metric}
              </td>
              <td style={{ padding: '6px 10px', fontFamily: F, fontSize: FS.sm, color: row.score != null ? T.cyan : T.dim, textAlign: 'right', fontWeight: 700 }}>
                {row.score != null ? row.score.toFixed(4) : '—'}
              </td>
              <td style={{ padding: '6px 10px', textAlign: 'center' }}>
                {row.complete ? (
                  <CheckCircle2 size={12} color="#22c55e" />
                ) : (
                  <Clock size={12} color={T.dim} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
