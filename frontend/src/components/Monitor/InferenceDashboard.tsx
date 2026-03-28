import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, EMPTY_BLOCK_METRICS } from '@/stores/metricsStore'
import AutoLineChart from './AutoLineChart'
import RawDataToggle from './RawDataToggle'

interface Props { blockId: string }

export default function InferenceDashboard({ blockId }: Props) {
  const blockMetrics = useMetricsStore((s) => s.metrics[blockId] ?? EMPTY_BLOCK_METRICS)

  const tokensSeries = blockMetrics['tokens/sec'] || []
  const requestsSeries = blockMetrics['requests'] || []
  const avgLenSeries = blockMetrics['avg_response_length'] || []

  const latestTokens = tokensSeries.length > 0 ? tokensSeries[tokensSeries.length - 1].value : null
  const totalRequests = requestsSeries.length > 0 ? requestsSeries[requestsSeries.length - 1].value : 0
  const avgLen = avgLenSeries.length > 0 ? avgLenSeries[avgLenSeries.length - 1].value : null

  return (
    <RawDataToggle blockId={blockId}>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Stats */}
        <div style={{
          display: 'flex', gap: 16, padding: '8px 12px',
          background: T.surface1, border: `1px solid ${T.border}`,
        }}>
          {latestTokens !== null && (
            <div>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Tokens/sec</span>
              <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {latestTokens.toFixed(1)}
              </div>
            </div>
          )}
          <div>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Requests</span>
            <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
              {totalRequests.toLocaleString()}
            </div>
          </div>
          {avgLen !== null && (
            <div>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Avg Length</span>
              <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {Math.round(avgLen)} tok
              </div>
            </div>
          )}
        </div>

        {/* Tokens/sec chart */}
        <AutoLineChart
          metricName="tokens/sec"
          blockId={blockId}
          color={T.cyan}
          height={200}
          title="TOKENS / SECOND"
        />
      </div>
    </RawDataToggle>
  )
}
