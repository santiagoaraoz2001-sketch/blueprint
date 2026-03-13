import { T, F, FS } from '@/lib/design-tokens'
import { useMetricsStore, EMPTY_BLOCK_METRICS } from '@/stores/metricsStore'
import RawDataToggle from './RawDataToggle'

interface Props { blockId: string }

export default function MergeDashboard({ blockId }: Props) {
  const blockMetrics = useMetricsStore((s) => s.metrics[blockId] ?? EMPTY_BLOCK_METRICS)

  const layerSeries = blockMetrics['layer'] || []
  const sizeSeries = blockMetrics['output_size_gb'] || []

  const currentLayer = layerSeries.length > 0 ? layerSeries[layerSeries.length - 1].value : 0
  const totalLayers = 32 // Default, can be overridden by metrics
  const outputSize = sizeSeries.length > 0 ? sizeSeries[sizeSeries.length - 1].value : null
  const progress = Math.min(1, currentLayer / totalLayers)

  return (
    <RawDataToggle blockId={blockId}>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Progress header */}
        <div style={{
          display: 'flex', gap: 16, padding: '8px 12px',
          background: T.surface1, border: `1px solid ${T.border}`,
          alignItems: 'center',
        }}>
          <div>
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Layer</span>
            <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
              {currentLayer}/{totalLayers}
            </div>
          </div>
          {outputSize !== null && (
            <div>
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, letterSpacing: '0.06em' }}>Output Size</span>
              <div style={{ fontFamily: F, fontSize: FS.lg, color: T.text, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                {outputSize.toFixed(1)} GB
              </div>
            </div>
          )}
          <div style={{ flex: 1 }} />
          <span style={{ fontFamily: F, fontSize: FS.md, color: T.cyan, fontWeight: 700 }}>
            {Math.round(progress * 100)}%
          </span>
        </div>

        {/* Large progress bar */}
        <div style={{
          padding: '16px 12px',
          background: T.surface1, border: `1px solid ${T.border}`,
        }}>
          <div style={{
            width: '100%', height: 16, background: T.surface3,
            borderRadius: 4, overflow: 'hidden',
          }}>
            <div style={{
              width: `${Math.round(progress * 100)}%`,
              height: '100%',
              background: `linear-gradient(90deg, #00BFA5, ${T.cyan})`,
              transition: 'width 0.3s ease',
              borderRadius: 4,
            }} />
          </div>
          <div style={{
            display: 'flex', justifyContent: 'space-between', marginTop: 6,
          }}>
            {Array.from({ length: Math.min(totalLayers, 8) }, (_, i) => {
              const layerNum = Math.round((i / 7) * totalLayers)
              return (
                <span key={i} style={{
                  fontFamily: F, fontSize: FS.xxs, color: layerNum <= currentLayer ? T.sec : T.dim,
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  L{layerNum}
                </span>
              )
            })}
          </div>
        </div>
      </div>
    </RawDataToggle>
  )
}
