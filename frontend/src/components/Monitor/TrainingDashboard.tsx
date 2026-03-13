import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, EMPTY_BLOCK_METRICS } from '@/stores/metricsStore'
import AutoLineChart from './AutoLineChart'
import RawDataToggle from './RawDataToggle'

interface Props { blockId: string }

export default function TrainingDashboard({ blockId }: Props) {
  const blockMetrics = useMetricsStore((s) => s.metrics[blockId] ?? EMPTY_BLOCK_METRICS)
  const block = useMetricsStore((s) => s.monitorExecutionOrder.find(b => b.id === blockId))

  const lossSeries = blockMetrics['train/loss'] || []
  const evalLossSeries = blockMetrics['eval/loss'] || []
  const lrSeries = blockMetrics['train/lr'] || []

  const latestLoss = lossSeries.length > 0 ? lossSeries[lossSeries.length - 1].value : null
  const latestLR = lrSeries.length > 0 ? lrSeries[lrSeries.length - 1].value : null
  const latestStep = lossSeries.length > 0 ? lossSeries[lossSeries.length - 1].step : 0

  return (
    <RawDataToggle blockId={blockId}>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Latest values */}
        <div style={{
          display: 'flex', gap: 16, padding: '8px 12px',
          background: T.surface1, border: `1px solid ${T.border}`,
        }}>
          {latestLoss !== null && (
            <div>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Loss</span>
              <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {latestLoss.toFixed(4)}
              </div>
            </div>
          )}
          {latestLR !== null && (
            <div>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>LR</span>
              <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {latestLR.toExponential(1)}
              </div>
            </div>
          )}
          <div style={{ flex: 1 }} />
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Progress</span>
            <div style={{ fontFamily: F, fontSize: FS.md, color: T.sec, fontVariantNumeric: 'tabular-nums' }}>
              Step {latestStep.toLocaleString()}
              {block && block.progress < 1 && ` — ${Math.round(block.progress * 100)}%`}
            </div>
          </div>
        </div>

        {/* Main loss chart */}
        <AutoLineChart
          metricName="train/loss"
          blockId={blockId}
          color="#00BFA5"
          height={240}
          title="TRAINING LOSS"
          overlayMetric={evalLossSeries.length > 0 ? 'eval/loss' : undefined}
          overlayColor="#F59E0B"
        />

        {/* Learning rate chart (if exists) */}
        {lrSeries.length > 0 && (
          <AutoLineChart
            metricName="train/lr"
            blockId={blockId}
            color="#3B82F6"
            height={120}
            title="LEARNING RATE"
          />
        )}
      </div>
    </RawDataToggle>
  )
}
