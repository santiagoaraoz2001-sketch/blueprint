import { useMemo } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, EMPTY_BLOCK_METRICS } from '@/stores/metricsStore'
import RawDataToggle from './RawDataToggle'
import { CheckCircle, Loader } from 'lucide-react'

interface Props { blockId: string }

interface BenchmarkResult {
  name: string
  score: number | null
  complete: boolean
}

export default function EvaluationDashboard({ blockId }: Props) {
  const blockMetrics = useMetricsStore((s) => s.metrics[blockId] ?? EMPTY_BLOCK_METRICS)

  const benchmarks = useMemo(() => {
    const results: BenchmarkResult[] = []

    for (const [metricName, series] of Object.entries(blockMetrics)) {
      // Parse benchmark/{name}/acc or benchmark/{name}/score patterns
      const match = metricName.match(/benchmark\/([^/]+)\/(.+)/)
      if (match) {
        const latest = series.length > 0 ? series[series.length - 1].value : null
        results.push({
          name: match[1],
          score: latest,
          complete: latest !== null,
        })
      } else {
        // Also accept direct metric names containing acc/score
        if (metricName.includes('acc') || metricName.includes('score') || metricName.includes('f1')) {
          const latest = series.length > 0 ? series[series.length - 1].value : null
          results.push({
            name: metricName,
            score: latest,
            complete: latest !== null,
          })
        }
      }
    }

    return results
  }, [blockMetrics])

  const completedCount = benchmarks.filter(b => b.complete).length
  const totalCount = benchmarks.length
  const avgScore = completedCount > 0
    ? benchmarks.filter(b => b.score !== null).reduce((sum, b) => sum + (b.score || 0), 0) / completedCount
    : null

  return (
    <RawDataToggle blockId={blockId}>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Summary */}
        <div style={{
          display: 'flex', gap: 16, padding: '8px 12px',
          background: T.surface1, border: `1px solid ${T.border}`,
          alignItems: 'center',
        }}>
          <div>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Completed</span>
            <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
              {completedCount}/{totalCount} benchmarks
            </div>
          </div>
          {avgScore !== null && (
            <div>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Average</span>
              <div style={{ fontFamily: F, fontSize: FS.lg, color: T.cyan, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {(avgScore * 100).toFixed(1)}%
              </div>
            </div>
          )}
          {/* Progress bar */}
          <div style={{ flex: 1 }}>
            <div style={{
              width: '100%', height: 4, background: T.surface3, borderRadius: 2,
              overflow: 'hidden',
            }}>
              <div style={{
                width: totalCount > 0 ? `${(completedCount / totalCount) * 100}%` : '0%',
                height: '100%', background: T.cyan,
                transition: 'width 0.3s ease',
              }} />
            </div>
          </div>
        </div>

        {/* Benchmark table */}
        {benchmarks.length === 0 ? (
          <div style={{
            padding: 24, textAlign: 'center',
            fontFamily: F, fontSize: FS.xs, color: T.dim,
          }}>
            Waiting for benchmark results...
          </div>
        ) : (
          <table style={{
            width: '100%', borderCollapse: 'collapse',
            fontFamily: F, fontSize: FS.xs,
          }}>
            <thead>
              <tr>
                <th style={{
                  padding: '6px 12px', textAlign: 'left',
                  borderBottom: `1px solid ${T.borderHi}`,
                  color: T.dim, fontWeight: 700, letterSpacing: '0.08em', fontSize: FS.xxs,
                }}>Benchmark</th>
                <th style={{
                  padding: '6px 12px', textAlign: 'right',
                  borderBottom: `1px solid ${T.borderHi}`,
                  color: T.dim, fontWeight: 700, letterSpacing: '0.08em', fontSize: FS.xxs,
                }}>Score</th>
                <th style={{
                  padding: '6px 12px', textAlign: 'center',
                  borderBottom: `1px solid ${T.borderHi}`,
                  color: T.dim, fontWeight: 700, letterSpacing: '0.08em', fontSize: FS.xxs,
                  width: 40,
                }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {benchmarks.map((b) => (
                <tr key={b.name} style={{ borderBottom: `1px solid ${T.border}` }}>
                  <td style={{ padding: '6px 12px', color: T.sec }}>{b.name}</td>
                  <td style={{
                    padding: '6px 12px', textAlign: 'right',
                    color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                  }}>
                    {b.score !== null ? `${(b.score * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td style={{ padding: '6px 12px', textAlign: 'center' }}>
                    {b.complete ? (
                      <CheckCircle size={12} color={T.green} />
                    ) : (
                      <Loader
                        size={12}
                        color={T.cyan}
                        style={{ animation: 'spin 1.5s linear infinite' }}
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </RawDataToggle>
  )
}
