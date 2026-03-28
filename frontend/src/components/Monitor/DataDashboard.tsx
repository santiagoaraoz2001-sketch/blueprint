import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, EMPTY_BLOCK_METRICS } from '@/stores/metricsStore'
import AutoLineChart from './AutoLineChart'
import RawDataToggle from './RawDataToggle'

interface Props { blockId: string }

export default function DataDashboard({ blockId }: Props) {
  const blockMetrics = useMetricsStore((s) => s.metrics[blockId] ?? EMPTY_BLOCK_METRICS)
  const rowsSeries = blockMetrics['rows_processed'] || []
  const rowsPerSecSeries = blockMetrics['rows/sec'] || []

  const totalRows = rowsSeries.length > 0 ? rowsSeries[rowsSeries.length - 1].value : 0
  const rowsPerSec = rowsPerSecSeries.length > 0 ? rowsPerSecSeries[rowsPerSecSeries.length - 1].value : null
  const targetRows = 100000 // Default target

  return (
    <RawDataToggle blockId={blockId}>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Progress */}
        <div style={{
          display: 'flex', gap: 16, padding: '8px 12px',
          background: T.surface1, border: `1px solid ${T.border}`,
          alignItems: 'center',
        }}>
          <div>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Rows</span>
            <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
              {totalRows.toLocaleString()}
            </div>
          </div>
          {rowsPerSec !== null && (
            <div>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Rows/sec</span>
              <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {Math.round(rowsPerSec).toLocaleString()}
              </div>
            </div>
          )}
          <div style={{ flex: 1 }}>
            <div style={{
              width: '100%', height: 4, background: T.surface3, borderRadius: 2,
              overflow: 'hidden',
            }}>
              <div style={{
                width: `${Math.min(100, (totalRows / targetRows) * 100)}%`,
                height: '100%', background: T.cyan,
                transition: 'width 0.3s ease',
              }} />
            </div>
          </div>
        </div>

        {/* Rows over time chart */}
        {rowsSeries.length > 3 && (
          <AutoLineChart
            metricName="rows_processed"
            blockId={blockId}
            color={T.cyan}
            height={160}
            title="ROWS PROCESSED"
          />
        )}

        {/* Preview table (simulated last 3 rows) */}
        <div style={{
          background: T.surface1, border: `1px solid ${T.border}`, padding: 8,
        }}>
          <div style={{
            fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
            color: T.dim, letterSpacing: '0.06em', marginBottom: 6,
          }}>
            SAMPLE ROWS
          </div>
          <table style={{
            width: '100%', borderCollapse: 'collapse', fontFamily: F, fontSize: FS.xxs,
          }}>
            <thead>
              <tr>
                {['#', 'Input', 'Output'].map(h => (
                  <th key={h} style={{
                    padding: '3px 8px', textAlign: 'left',
                    borderBottom: `1px solid ${T.borderHi}`, color: T.dim,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[1, 2, 3].map(i => (
                <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                  <td style={{ padding: '3px 8px', color: T.dim }}>{Math.max(0, totalRows - 3 + i)}</td>
                  <td style={{ padding: '3px 8px', color: T.sec, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    Sample input {Math.max(0, totalRows - 3 + i)}...
                  </td>
                  <td style={{ padding: '3px 8px', color: T.sec, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    Processed output...
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </RawDataToggle>
  )
}
